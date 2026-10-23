"""Analytics formulas on hand-built data where every expected figure is known."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.financial_analytics import compute_analytics, default_period, next_occurrence
from tests.factories import AS_OF, CARD, account, customer, d, monthly_history, obligation, profile, txn


def test_default_period_is_last_complete_months() -> None:
    assert default_period(AS_OF, 6) == (date(2026, 4, 1), date(2026, 9, 30))
    assert default_period(date(2026, 1, 3), 3) == (date(2025, 10, 1), date(2025, 12, 31))


def test_totals_averages_and_savings_rate() -> None:
    result = compute_analytics(customer(), AS_OF)
    assert result.period.months_with_data == 6
    assert result.totals.total_income == d("360000.00")
    assert result.totals.total_expenses == d("162000.00")
    assert result.totals.net_observed_cash_flow == d("198000.00")
    assert result.monthly_averages.income == d("60000.00")
    assert result.monthly_averages.essential_expenses == d("23000.00")
    assert result.monthly_averages.discretionary_expenses == d("4000.00")
    assert result.savings_rate.status == "calculated"
    assert result.savings_rate.value_pct == d("55.0")


def test_partial_current_month_is_excluded_from_period_but_shown_in_trend() -> None:
    result = compute_analytics(customer(), AS_OF)
    assert result.monthly_trend[-1].month == "2026-10"
    assert result.monthly_trend[-1].is_partial
    assert result.totals.total_income == d("360000.00")  # October salary not counted


def test_refunds_transfers_duplicates_and_reversals_do_not_inflate_totals() -> None:
    base = monthly_history()
    extra = [
        txn(date(2026, 9, 20), "2500.00", "debit", "purchase", "shopping", txn_id="shoe"),
        txn(date(2026, 9, 25), "2500.00", "credit", "refund", "shopping"),  # refund nets the purchase
        txn(date(2026, 9, 21), "999.00", "debit", "purchase", "dining", description="UPI/DUP/1"),
        txn(date(2026, 9, 21), "999.00", "debit", "purchase", "dining", description="UPI/DUP/1"),  # duplicate
        txn(date(2026, 9, 22), "700.00", "debit", "purchase", "shopping", txn_id="failed"),
        txn(date(2026, 9, 22), "700.00", "credit", "reversal", "shopping", reverses="failed"),
        txn(date(2026, 9, 18), "5000.00", "debit", "transfer_out", "transfer", group="cc"),
        txn(date(2026, 9, 18), "5000.00", "credit", "transfer_in", "transfer", account=CARD, group="cc"),
    ]
    result = compute_analytics(
        customer(base + extra, accounts=[account(), account(CARD, "credit_card", "0.00")]), AS_OF
    )
    assert result.totals.total_expenses == d("162999.00")  # only the one genuine 999 dining spend added
    assert result.totals.refunds_netted == d("2500.00")
    assert result.totals.excluded_duplicates == d("999.00")
    assert result.totals.excluded_reversal_pairs == 1
    assert result.totals.excluded_internal_transfers == d("5000.00")
    assert result.totals.total_income == d("360000.00")


def test_missing_months_are_not_treated_as_zero() -> None:
    rows = [t for t in monthly_history() if t.posted_on.month != 6]  # June has no data at all
    result = compute_analytics(customer(rows), AS_OF)
    assert result.period.months_in_period == 6
    assert result.period.months_with_data == 5
    assert result.monthly_averages.income == d("60000.00")  # averaged over 5 observed months, not 6
    june = next(p for p in result.monthly_trend if p.month == "2026-06")
    assert june.has_data is False


def test_short_history_produces_explicit_unknowns() -> None:
    result = compute_analytics(customer(monthly_history(months=2)), AS_OF)
    assert result.savings_rate.value_pct is None
    assert result.savings_rate.status == "insufficient_data"
    assert result.emergency_fund.status == "unknown"
    assert result.savings_capacity.estimated_monthly_capacity is None
    assert result.data_quality.confidence == "low"
    assert "short_history" in {i.code for i in result.data_quality.issues}


def test_missing_balance_makes_emergency_fund_unknown_not_zero() -> None:
    result = compute_analytics(customer(accounts=[account(balance=None)]), AS_OF)
    assert result.balances.reported_liquid_balance is None
    assert result.emergency_fund.status == "unknown"
    assert result.emergency_fund.coverage_months is None
    assert result.data_quality.balance_status == "missing"
    assert result.data_quality.confidence == "medium"


def test_stale_transactions_lower_confidence() -> None:
    rows = monthly_history(end_month=date(2026, 7, 1), include_current=False)
    result = compute_analytics(customer(rows), AS_OF)
    assert result.data_quality.freshness == "stale"
    assert result.data_quality.days_since_last_transaction == (AS_OF - date(2026, 7, 15)).days
    assert result.data_quality.confidence == "low"


def test_emergency_fund_coverage_and_target() -> None:
    result = compute_analytics(customer(accounts=[account(balance="46000.00")]), AS_OF)
    ef = result.emergency_fund
    assert ef.coverage_months == d("2.0")  # 46000 / 23000
    assert ef.target_months == 3
    assert ef.gap_amount == d("23000.00")
    assert ef.status == "building"
    irregular = compute_analytics(
        customer(accounts=[account(balance="46000.00")], fin_profile=profile(income_pattern="irregular")), AS_OF
    )
    assert irregular.emergency_fund.target_months == 6


def test_reconciliation_difference_between_reported_and_estimated_balance() -> None:
    rows = monthly_history()
    net = sum((t.signed_amount for t in rows), Decimal("0"))
    consistent = compute_analytics(customer(rows, accounts=[account(balance=str(net), opening="0.00")]), AS_OF)
    assert consistent.balances.accounts[0].reconciliation_difference == d("0.00")
    assert "balance_mismatch" not in {i.code for i in consistent.data_quality.issues}
    off = compute_analytics(customer(rows, accounts=[account(balance=str(net + 1), opening="0.00")]), AS_OF)
    assert off.balances.accounts[0].reconciliation_difference == d("1.00")
    assert "balance_mismatch" in {i.code for i in off.data_quality.issues}


def test_upcoming_obligations_roll_forward_and_capacity_provision() -> None:
    obligations = [
        obligation("annual", "24000.00", "annual", date(2026, 11, 5), "Insurance"),
        obligation("rent", "15000.00", "monthly", date(2026, 8, 3), "Rent"),  # stale date rolls forward
        obligation("old", "9000.00", "one_time", date(2026, 9, 1), "Past one-off"),
    ]
    result = compute_analytics(customer(obligations=obligations), AS_OF)
    names = {o.name: o for o in result.upcoming_obligations.items}
    assert set(names) == {"Insurance", "Rent"}
    assert names["Rent"].due_date == date(2026, 11, 3)
    assert result.upcoming_obligations.total_due == d("39000.00")
    assert next_occurrence(obligations[2], AS_OF) is None
    capacity = result.savings_capacity
    assert capacity.non_monthly_obligation_provision == d("2000.00")  # 24000 / 12
    assert capacity.estimated_monthly_capacity == d("31000.00")  # 33000 net - 2000 provision


def test_capacity_uses_lower_recent_average() -> None:
    rows = monthly_history()
    rows += [txn(date(2026, m, 20), "21000.00", "debit", "purchase", "travel") for m in (7, 8, 9)]
    result = compute_analytics(customer(rows), AS_OF)
    assert result.savings_capacity.recent_3_month_net_cash_flow == d("12000.00")
    assert result.savings_capacity.estimated_monthly_capacity == d("12000.00")


def test_recurring_subscription_detection() -> None:
    rows = monthly_history()
    rows += [
        txn(date(2026, m, 14), "649.00", "debit", "purchase", "subscriptions", merchant="StreamFlix")
        for m in (6, 7, 8, 9, 10)
    ]
    rows += [
        txn(date(2026, m, 14), amt, "debit", "purchase", "dining", merchant="Random Eats")
        for m, amt in ((7, "200.00"), (8, "900.00"), (9, "450.00"))
    ]
    result = compute_analytics(customer(rows), AS_OF)
    recurring = {r.merchant: r for r in result.recurring_expenses}
    assert "Streamflix" in recurring
    assert recurring["Streamflix"].is_subscription
    assert recurring["Streamflix"].average_amount == d("649.00")
    assert "Random Eats" not in recurring  # amounts vary too much


def test_month_over_month_change() -> None:
    rows = monthly_history()
    rows.append(txn(date(2026, 9, 25), "2700.00", "debit", "purchase", "shopping"))
    result = compute_analytics(customer(rows), AS_OF)
    september = next(m for m in result.month_over_month if m.month == "2026-09")
    assert september.previous_expenses == d("27000.00")
    assert september.change_amount == d("2700.00")
    assert september.change_pct == d("10.0")


def test_many_small_amounts_sum_exactly() -> None:
    rows = monthly_history()
    rows += [
        txn(date(2026, 9, 2), "0.10", "debit", "purchase", "other_expense", description=f"FEE/{i}") for i in range(10)
    ]
    result = compute_analytics(customer(rows), AS_OF)
    assert result.totals.total_expenses == d("162001.00")


def test_invalid_period_rejected() -> None:
    with pytest.raises(ValueError):
        compute_analytics(customer(), AS_OF, start_date=date(2026, 9, 1), end_date=date(2026, 8, 1))


def test_no_income_gives_explicit_status() -> None:
    rows = [t for t in monthly_history() if t.transaction_type != "salary"]
    result = compute_analytics(customer(rows), AS_OF)
    assert result.savings_rate.status == "no_income"
    assert result.savings_rate.value_pct is None
    # Unobserved income is unknown, never a silent zero; expenses are still reported.
    assert result.monthly_averages.income is None
    assert result.monthly_averages.net_observed_cash_flow is None
    assert result.monthly_averages.expenses == d("27000.00")
