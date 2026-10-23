"""Financial analytics engine.

Pure and deterministic: the same CustomerFinancialData + as_of + period always
produces the same AnalyticsResult. Aggregation runs in pandas on integer paise
(exact), and results are converted back to Decimal rupees.

Formulas are documented in docs/recommendation-engine.md and docs/database-design.md.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from app.models.domain import CustomerFinancialData, GoalRecord, ObligationRecord
from app.schemas.analytics import (
    AccountBalance,
    AnalyticsResult,
    BalanceSummary,
    CashFlowTotals,
    CategorySpend,
    DataQualityOut,
    EmergencyFund,
    GoalProgress,
    IncomeStability,
    MonthlyAverages,
    MonthlyTrendPoint,
    MonthOverMonth,
    PeriodInfo,
    QualityIssueOut,
    RecurringExpense,
    SavingsCapacity,
    SavingsRate,
    UpcomingObligation,
    UpcomingObligations,
)
from app.services.data_quality import (
    BALANCE_STALE_DAYS,
    MIN_HISTORY_MONTHS_FOR_TRENDS,
    QualityIssue,
    assess_data_quality,
)
from app.services.goal_planning import GoalPlan, plan_goal
from app.services.spending_categorization import ClassifiedTxn, classify_transactions
from app.utils.dates import add_months, month_key, month_start
from app.utils.money import ZERO, from_paise, to_money, to_paise

DEFAULT_WINDOW_MONTHS = 6
UPCOMING_HORIZON_DAYS = 30
BASE_EMERGENCY_TARGET_MONTHS = 3
ELEVATED_EMERGENCY_TARGET_MONTHS = 6
MAX_SHARE_OF_CAPACITY_FOR_SUGGESTIONS = Decimal("0.50")
EMERGENCY_BUILD_MONTHS = 12
RECURRING_MIN_MONTHS = 3
RECURRING_MAX_VARIATION = Decimal("0.15")
RECURRING_ACTIVE_DAYS = 45
INCOME_CV_VARIABLE = Decimal("0.25")

FREQUENCY_MONTHS = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "annual": 12}


def _pct(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def default_period(as_of: date, window_months: int) -> tuple[date, date]:
    """Last `window_months` *complete* calendar months before as_of's month."""
    current_month = month_start(as_of)
    return add_months(current_month, -window_months), current_month - timedelta(days=1)


def months_in_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    cursor = month_start(start)
    while cursor <= end:
        months.append(month_key(cursor))
        cursor = add_months(cursor, 1)
    return months


def next_occurrence(obligation: ObligationRecord, as_of: date) -> date | None:
    """Roll a recurring due date forward to the first occurrence on/after as_of."""
    due = obligation.next_due_date
    step = FREQUENCY_MONTHS.get(obligation.frequency)
    if step is None:  # one_time
        return due if due >= as_of else None
    while due < as_of:
        due = add_months(due, step)
    if obligation.end_date and due > obligation.end_date:
        return None
    return due


def emergency_target_months(data: CustomerFinancialData) -> tuple[int, str]:
    profile = data.profile
    if profile and profile.income_pattern == "irregular":
        return ELEVATED_EMERGENCY_TARGET_MONTHS, "Irregular income: target of 6 months of essential expenses."
    if profile and (profile.dependents or 0) >= 2:
        return ELEVATED_EMERGENCY_TARGET_MONTHS, "Two or more dependents: target of 6 months of essential expenses."
    return BASE_EMERGENCY_TARGET_MONTHS, "Standard target of 3 months of essential expenses."


def _frame(classified: list[ClassifiedTxn]) -> pd.DataFrame:
    rows = [
        {
            "posted_on": c.txn.posted_on,
            "month": month_key(c.txn.posted_on),
            "flow": c.flow,
            "category": c.category,
            "group": c.category_group,
            "paise": to_paise(c.txn.amount),
            "direction": c.txn.direction,
            "merchant": c.txn.merchant_name or c.txn.description.split("/")[0],
            "exclusion": c.exclusion_reason or "",
            "savings_transfer": c.is_savings_transfer,
        }
        for c in classified
    ]
    columns = [
        "posted_on",
        "month",
        "flow",
        "category",
        "group",
        "paise",
        "direction",
        "merchant",
        "exclusion",
        "savings_transfer",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["paise"] = frame["paise"].astype("int64")
    # Expense contribution: expenses add, refunds subtract (net spend per category).
    frame["spend"] = 0
    frame.loc[frame["flow"] == "expense", "spend"] = frame["paise"]
    frame.loc[frame["flow"] == "refund", "spend"] = -frame["paise"]
    frame["income"] = 0
    frame.loc[frame["flow"] == "income", "income"] = frame["paise"]
    frame["spend"] = frame["spend"].astype("int64")
    frame["income"] = frame["income"].astype("int64")
    return frame


def _monthly_table(frame: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    counted = frame[frame["flow"] != "excluded"]
    base = pd.DataFrame(index=pd.Index(months, name="month"))
    agg = counted.groupby("month").agg(income=("income", "sum"), spend=("spend", "sum"), txn_count=("paise", "size"))
    essential = counted[counted["group"] == "essential"].groupby("month")["spend"].sum().rename("essential")
    discretionary = counted[counted["group"] == "discretionary"].groupby("month")["spend"].sum().rename("discretionary")
    table = base.join(agg).join(essential).join(discretionary)
    table["has_data"] = table["txn_count"].notna() & (table["txn_count"] > 0)
    return table.fillna(0).astype({"income": "int64", "spend": "int64", "essential": "int64", "discretionary": "int64"})


def _detect_recurring(frame: pd.DataFrame, as_of: date) -> list[RecurringExpense]:
    window_start = add_months(as_of, -6)
    spend = frame[
        (frame["flow"] == "expense") & (frame["posted_on"] > window_start) & (frame["posted_on"] <= as_of)
    ].copy()
    if spend.empty:
        return []
    spend["merchant_key"] = spend["merchant"].str.upper().str.replace(r"[^A-Z ]+", " ", regex=True).str.strip()
    results: list[RecurringExpense] = []
    for merchant, group in spend.groupby("merchant_key", sort=True):
        group = group.sort_values("posted_on")
        months_observed = group["month"].nunique()
        if months_observed < RECURRING_MIN_MONTHS:
            continue
        amounts = [int(x) for x in group["paise"]]
        median = int(statistics.median(amounts))
        if median <= 0:
            continue
        variation = Decimal(max(amounts) - min(amounts)) / Decimal(median)
        if variation > RECURRING_MAX_VARIATION:
            continue
        dates = list(group["posted_on"])
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        median_gap = statistics.median(gaps) if gaps else 0
        if not 25 <= median_gap <= 35:
            continue
        last = dates[-1]
        if (as_of - last).days > RECURRING_ACTIVE_DAYS:
            continue
        category = str(group["category"].mode().iloc[0])
        results.append(
            RecurringExpense(
                merchant=str(merchant).title(),
                category=category,
                average_amount=from_paise(round(sum(amounts) / len(amounts))),
                occurrences=len(amounts),
                months_observed=int(months_observed),
                last_date=last,
                next_expected_date=last + timedelta(days=round(median_gap)),
                is_subscription=category == "subscriptions",
                amount_variation_pct=(variation * 100).quantize(Decimal("0.1")),
            )
        )
    results.sort(key=lambda r: (-r.average_amount, r.merchant))
    return results


def _account_balances(
    data: CustomerFinancialData, classified: list[ClassifiedTxn], as_of: date
) -> tuple[BalanceSummary, list[str]]:
    mismatches: list[str] = []
    accounts_out: list[AccountBalance] = []
    by_account: dict[str, list[ClassifiedTxn]] = {}
    for c in classified:
        by_account.setdefault(c.txn.account_id, []).append(c)
    for account in sorted(data.accounts, key=lambda a: (a.account_type, a.masked_number)):
        relevant = [
            c
            for c in by_account.get(account.id, [])
            if c.exclusion_reason != "probable_duplicate" and account.opening_balance_date <= c.txn.posted_on <= as_of
        ]
        estimated = to_money(account.opening_balance) + sum((c.txn.signed_amount for c in relevant), ZERO)
        stale = None
        difference = None
        if account.current_balance is not None and account.balance_as_of is not None:
            stale = (as_of - account.balance_as_of.date()).days > BALANCE_STALE_DAYS
            latest_txn = max((c.txn.posted_on for c in relevant), default=None)
            if latest_txn is None or account.balance_as_of.date() >= latest_txn:
                difference = to_money(account.current_balance) - estimated
                if difference != ZERO:
                    mismatches.append(account.id)
        accounts_out.append(
            AccountBalance(
                account_id=account.id,
                nickname=account.nickname,
                account_type=account.account_type,
                masked_number=account.masked_number,
                is_liquid=account.is_liquid,
                reported_balance=account.current_balance,
                balance_as_of=account.balance_as_of,
                balance_is_stale=stale,
                estimated_balance_from_transactions=to_money(estimated),
                reconciliation_difference=difference,
            )
        )
    liquid = [a for a in data.accounts if a.is_liquid and a.status == "active"]
    liquid_status = "fresh"
    liquid_total: Decimal | None = None
    if not liquid or any(a.current_balance is None for a in liquid):
        liquid_status = "missing"
    else:
        liquid_total = sum((to_money(a.current_balance) for a in liquid if a.current_balance is not None), ZERO)
        if any(a.balance_as_of and (as_of - a.balance_as_of.date()).days > BALANCE_STALE_DAYS for a in liquid):
            liquid_status = "stale"
    cards = [a for a in data.accounts if a.account_type == "credit_card" and a.status == "active"]
    card_outstanding = None
    if cards and all(a.current_balance is not None for a in cards):
        card_outstanding = sum(
            (-to_money(a.current_balance) for a in cards if a.current_balance is not None and a.current_balance < 0),
            ZERO,
        )
    return (
        BalanceSummary(
            reported_liquid_balance=liquid_total,
            liquid_balance_status=liquid_status,  # type: ignore[arg-type]
            credit_card_outstanding=card_outstanding,
            accounts=accounts_out,
        ),
        mismatches,
    )


def plan_all_goals(goals: list[GoalRecord], as_of: date, allocatable: Decimal | None) -> list[GoalPlan]:
    """Plan goals in priority order, sharing one capacity pool so the same surplus
    is never suggested twice."""
    remaining = allocatable
    plans: list[GoalPlan] = []
    ordered = sorted(goals, key=lambda g: (g.priority, g.target_date or date.max, g.name))
    for goal in ordered:
        plan = plan_goal(goal, as_of, remaining)
        if remaining is not None and plan.suggested_increase:
            remaining = max(remaining - plan.suggested_increase, ZERO)
        plans.append(plan)
    return plans


def compute_analytics(
    data: CustomerFinancialData,
    as_of: date,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    start_date: date | None = None,
    end_date: date | None = None,
) -> AnalyticsResult:
    if start_date is None or end_date is None:
        start_date, end_date = default_period(as_of, window_months)
    end_date = min(end_date, as_of)
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    classified = classify_transactions(data.transactions, data.accounts)
    usable = [c for c in classified if c.txn.posted_on <= as_of]
    frame = _frame(usable)

    # History = complete calendar months with data (the current partial month does not count).
    counted_months = frame.loc[(frame["flow"] != "excluded") & (frame["month"] != month_key(as_of)), "month"]
    history_months = int(counted_months.nunique()) if not frame.empty else 0
    quality = assess_data_quality(data, classified, as_of, history_months)

    in_period = frame[(frame["posted_on"] >= start_date) & (frame["posted_on"] <= end_date)]
    period_months = months_in_range(start_date, end_date)
    monthly = _monthly_table(in_period, period_months)
    months_with_data = int(monthly["has_data"].sum())

    total_income = int(in_period["income"].sum())
    total_spend = int(in_period["spend"].sum())
    refunds = int(in_period.loc[in_period["flow"] == "refund", "paise"].sum())
    # Count each internal transfer once (its debit leg).
    internal = int(
        in_period.loc[
            (in_period["exclusion"] == "internal_transfer") & (in_period["direction"] == "debit"), "paise"
        ].sum()
    )
    duplicates = int(in_period.loc[in_period["exclusion"] == "probable_duplicate", "paise"].sum())
    reversal_pairs = int((in_period["exclusion"] == "reversal").sum())

    totals = CashFlowTotals(
        total_income=from_paise(total_income),
        total_expenses=from_paise(total_spend),
        refunds_netted=from_paise(refunds),
        net_observed_cash_flow=from_paise(total_income - total_spend),
        excluded_internal_transfers=from_paise(internal),
        excluded_duplicates=from_paise(duplicates),
        excluded_reversal_pairs=reversal_pairs,
    )

    # --- Monthly averages over months that actually have data (missing != zero) ---
    with_data = monthly[monthly["has_data"]]

    def avg(column: str) -> Decimal | None:
        if months_with_data == 0:
            return None
        return from_paise(round(int(with_data[column].sum()) / months_with_data))

    avg_income, avg_spend = avg("income"), avg("spend")
    averages = MonthlyAverages(
        income=avg_income,
        expenses=avg_spend,
        essential_expenses=avg("essential"),
        discretionary_expenses=avg("discretionary"),
        net_observed_cash_flow=(avg_income - avg_spend) if avg_income is not None and avg_spend is not None else None,
        basis_months=months_with_data,
    )

    # --- Savings rate ---
    if months_with_data < MIN_HISTORY_MONTHS_FOR_TRENDS:
        savings_rate = SavingsRate(
            value_pct=None,
            status="insufficient_data",
            reason=f"Needs at least {MIN_HISTORY_MONTHS_FOR_TRENDS} months with data "
            f"in the period (found {months_with_data}).",
        )
    elif total_income <= 0:
        savings_rate = SavingsRate(value_pct=None, status="no_income", reason="No income was observed in the period.")
    else:
        savings_rate = SavingsRate(value_pct=_pct(total_income - total_spend, total_income), status="calculated")

    # --- Spending by category (net of refunds) ---
    counted = in_period[in_period["flow"].isin(["expense", "refund"])]
    by_category: list[CategorySpend] = []
    if not counted.empty:
        grouped = counted.groupby(["category", "group"]).agg(amount=("spend", "sum"), count=("paise", "size"))
        for (category, group), row in grouped.sort_values("amount", ascending=False).iterrows():
            amount = int(row["amount"])
            if amount <= 0:
                continue
            by_category.append(
                CategorySpend(
                    category=str(category),
                    group=str(group),
                    amount=from_paise(amount),
                    share_pct=_pct(amount, total_spend),
                    transaction_count=int(row["count"]),
                )
            )

    # --- Trend (period months + current partial month) and month-over-month ---
    trend_months = months_in_range(start_date, as_of)
    trend_table = _monthly_table(
        frame[(frame["posted_on"] >= start_date) & (frame["posted_on"] <= as_of)], trend_months
    )
    current_key = month_key(as_of)
    trend = [
        MonthlyTrendPoint(
            month=str(m),
            income=from_paise(int(r["income"])),
            expenses=from_paise(int(r["spend"])),
            essential_expenses=from_paise(int(r["essential"])),
            discretionary_expenses=from_paise(int(r["discretionary"])),
            net_observed_cash_flow=from_paise(int(r["income"]) - int(r["spend"])),
            has_data=bool(r["has_data"]),
            is_partial=(str(m) == current_key),
        )
        for m, r in trend_table.iterrows()
    ]
    mom: list[MonthOverMonth] = []
    previous: MonthlyTrendPoint | None = None
    for point in (p for p in trend if not p.is_partial):
        if previous is not None and previous.has_data and point.has_data:
            change = point.expenses - previous.expenses
            pct = (change / previous.expenses * 100).quantize(Decimal("0.1")) if previous.expenses else None
            mom.append(
                MonthOverMonth(
                    month=point.month,
                    expenses=point.expenses,
                    previous_expenses=previous.expenses,
                    change_amount=change,
                    change_pct=pct,
                )
            )
        elif point.has_data:
            mom.append(
                MonthOverMonth(
                    month=point.month,
                    expenses=point.expenses,
                    previous_expenses=None,
                    change_amount=None,
                    change_pct=None,
                )
            )
        previous = point

    # --- Income stability ---
    income_months = [int(v) for v in with_data["income"] if int(v) > 0]
    cv: Decimal | None = None
    pattern = "insufficient_data"
    if len(income_months) >= MIN_HISTORY_MONTHS_FOR_TRENDS:
        mean = statistics.fmean(income_months)
        cv = Decimal(str(round(statistics.pstdev(income_months) / mean, 4))) if mean else None
        pattern = "variable" if cv is not None and cv > INCOME_CV_VARIABLE else "stable"
    income_stability = IncomeStability(
        months_with_income=len(income_months),
        coefficient_of_variation=cv,
        pattern=pattern,  # type: ignore[arg-type]
        declared_monthly_income=data.profile.declared_monthly_income if data.profile else None,
    )

    balances, mismatches = _account_balances(data, classified, as_of)
    if mismatches:  # report reconciliation issues alongside the other quality checks
        quality.issues.append(
            QualityIssue(
                code="balance_mismatch",
                severity="warning",
                message="Reported balance differs from the balance reconstructed from transactions.",
                count=len(mismatches),
            )
        )

    # --- Emergency fund ---
    target_months, target_reason = emergency_target_months(data)
    ef_assumptions = [
        target_reason,
        "Essential expenses = rent, utilities, groceries, transport, insurance, healthcare, education, "
        "childcare and loan EMIs, averaged over months with data.",
        "Only active savings/current account balances count as liquid; fixed deposits and credit limits are excluded.",
    ]
    avg_essential = averages.essential_expenses
    if balances.reported_liquid_balance is None:
        emergency = EmergencyFund(
            liquid_balance=None,
            average_monthly_essential_expenses=avg_essential,
            coverage_months=None,
            target_months=target_months,
            target_amount=None,
            gap_amount=None,
            status="unknown",
            reason="Liquid account balance is not reported.",
            assumptions=ef_assumptions,
        )
    elif avg_essential is None or months_with_data < MIN_HISTORY_MONTHS_FOR_TRENDS or avg_essential <= 0:
        emergency = EmergencyFund(
            liquid_balance=balances.reported_liquid_balance,
            average_monthly_essential_expenses=avg_essential,
            coverage_months=None,
            target_months=target_months,
            target_amount=None,
            gap_amount=None,
            status="unknown",
            reason="Not enough expense history to estimate essential spending.",
            assumptions=ef_assumptions,
        )
    else:
        liquid = balances.reported_liquid_balance
        coverage = (liquid / avg_essential).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        target_amount = to_money(avg_essential * target_months)
        gap = max(target_amount - liquid, ZERO)
        status = "sufficient" if coverage >= target_months else ("building" if coverage >= 1 else "insufficient")
        if balances.liquid_balance_status == "stale":
            ef_assumptions.append("A reported balance is older than 7 days; coverage may have changed.")
        emergency = EmergencyFund(
            liquid_balance=liquid,
            average_monthly_essential_expenses=avg_essential,
            coverage_months=coverage,
            target_months=target_months,
            target_amount=target_amount,
            gap_amount=gap,
            status=status,  # type: ignore[arg-type]
            reason=None,
            assumptions=ef_assumptions,
        )

    # --- Savings capacity (conservative estimate, never guaranteed) ---
    provision = ZERO
    provision_parts: list[str] = []
    for ob in data.obligations:
        if ob.status != "active":
            continue
        occurrence = next_occurrence(ob, as_of)
        if occurrence is None:
            continue
        if ob.frequency in {"quarterly", "half_yearly", "annual"}:
            part = to_money(ob.amount / FREQUENCY_MONTHS[ob.frequency])
        elif ob.frequency == "one_time" and occurrence <= add_months(as_of, 6):
            months_to_due = max((occurrence - as_of).days // 30, 1)
            part = to_money(ob.amount / months_to_due)
        else:
            continue  # monthly commitments are already visible in observed expenses
        provision += part
        provision_parts.append(f"{ob.name}: {part}")

    recent_months = [m for m in period_months[-3:] if bool(monthly.loc[m, "has_data"])]
    recent_net = None
    if len(recent_months) == 3:
        recent = monthly.loc[recent_months]
        recent_net = from_paise(round((int(recent["income"].sum()) - int(recent["spend"].sum())) / 3))
    savings_transfers = in_period[in_period["savings_transfer"]]
    observed_transfers = (
        from_paise(round(int(savings_transfers["paise"].sum()) / months_with_data)) if months_with_data else None
    )

    capacity_calc: dict[str, str] = {}
    capacity: Decimal | None = None
    capacity_reason: str | None = None
    if quality.confidence == "low":
        capacity_reason = "Data confidence is low: " + "; ".join(quality.confidence_reasons[:2])
    elif averages.net_observed_cash_flow is None or months_with_data < MIN_HISTORY_MONTHS_FOR_TRENDS:
        capacity_reason = "Not enough months with data to estimate capacity."
    else:
        basis = averages.net_observed_cash_flow
        if recent_net is not None and recent_net < basis:
            basis = recent_net
            capacity_calc["basis"] = f"lower of period average and last-3-month average = {basis}"
        else:
            capacity_calc["basis"] = f"period average net observed cash flow = {basis}"
        capacity = max(basis - provision, ZERO)
        capacity_calc["provision_for_non_monthly_obligations"] = (
            " + ".join(provision_parts) + f" = {provision}" if provision_parts else "0.00"
        )
        capacity_calc["estimated_monthly_capacity"] = f"max({basis} - {provision}, 0) = {capacity}"

    savings_capacity = SavingsCapacity(
        average_monthly_net_cash_flow=averages.net_observed_cash_flow,
        recent_3_month_net_cash_flow=recent_net,
        non_monthly_obligation_provision=provision,
        estimated_monthly_capacity=capacity,
        observed_monthly_transfers_to_savings=observed_transfers,
        reason=capacity_reason,
        calculation=capacity_calc,
    )

    # --- Upcoming obligations ---
    horizon = as_of + timedelta(days=UPCOMING_HORIZON_DAYS)
    upcoming_items: list[UpcomingObligation] = []
    for ob in data.obligations:
        if ob.status != "active":
            continue
        occurrence = next_occurrence(ob, as_of)
        if occurrence is None or occurrence > horizon:
            continue
        upcoming_items.append(
            UpcomingObligation(
                obligation_id=ob.id,
                name=ob.name,
                obligation_type=ob.obligation_type,
                amount=to_money(ob.amount),
                frequency=ob.frequency,
                due_date=occurrence,
                days_until_due=(occurrence - as_of).days,
                is_essential=ob.is_essential,
            )
        )
    upcoming_items.sort(key=lambda o: (o.due_date, o.name))
    upcoming = UpcomingObligations(
        horizon_days=UPCOMING_HORIZON_DAYS,
        items=upcoming_items,
        total_due=sum((o.amount for o in upcoming_items), ZERO),
    )

    # --- Goals: share the capacity pool, emergency fund first ---
    allocatable = goal_allocatable_capacity(capacity, emergency)
    plans = plan_all_goals([g for g in data.goals if g.status != "cancelled"], as_of, allocatable)

    return AnalyticsResult(
        customer_id=data.customer_id,
        period=PeriodInfo(
            start_date=start_date,
            end_date=end_date,
            as_of=as_of,
            months_in_period=len(period_months),
            months_with_data=months_with_data,
        ),
        totals=totals,
        monthly_averages=averages,
        savings_rate=savings_rate,
        spending_by_category=by_category,
        monthly_trend=trend,
        month_over_month=mom,
        recurring_expenses=_detect_recurring(frame, as_of),
        income_stability=income_stability,
        balances=balances,
        emergency_fund=emergency,
        savings_capacity=savings_capacity,
        upcoming_obligations=upcoming,
        goals=[GoalProgress(**asdict(p)) for p in plans],
        data_quality=DataQualityOut(
            latest_transaction_date=quality.latest_transaction_date,
            days_since_last_transaction=quality.days_since_last_transaction,
            freshness=quality.freshness,
            history_months=quality.history_months,
            profile_age_days=quality.profile_age_days,
            balance_status=quality.balance_status,
            issues=[QualityIssueOut(**asdict(i)) for i in quality.issues],
            confidence=quality.confidence,
            confidence_reasons=quality.confidence_reasons,
        ),
    )


def emergency_reserve(capacity: Decimal | None, emergency: EmergencyFund) -> Decimal:
    """Portion of the suggestion pool reserved for building the emergency fund."""
    if capacity is None or emergency.status not in {"insufficient", "building"} or not emergency.gap_amount:
        return ZERO
    pool = to_money(capacity * MAX_SHARE_OF_CAPACITY_FOR_SUGGESTIONS)
    return min(pool, to_money(emergency.gap_amount / EMERGENCY_BUILD_MONTHS))


def goal_allocatable_capacity(capacity: Decimal | None, emergency: EmergencyFund) -> Decimal | None:
    if capacity is None:
        return None
    pool = to_money(capacity * MAX_SHARE_OF_CAPACITY_FOR_SUGGESTIONS)
    return max(pool - emergency_reserve(capacity, emergency), ZERO)
