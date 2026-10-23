"""Transaction classification.

Decides, for every transaction, whether it counts as income, an expense, a
refund (negative expense), or is excluded from cash-flow metrics because it is
an internal transfer, a probable duplicate import, or part of a reversal pair.
This is the single place that prevents double counting.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.models.domain import AccountRecord, TxnRecord

INCOME_TYPES = frozenset({"salary", "business_income", "pension", "interest", "other_income"})
EXPENSE_TYPES = frozenset({"purchase", "bill_payment", "loan_payment", "fee"})
TRANSFER_TYPES = frozenset({"transfer_in", "transfer_out"})

INCOME_CATEGORIES = frozenset({"salary", "business_income", "pension", "interest", "other_income"})
ESSENTIAL_CATEGORIES = frozenset(
    {"rent", "utilities", "groceries", "transport", "insurance", "healthcare", "education", "childcare", "loan_emi"}
)
DISCRETIONARY_CATEGORIES = frozenset(
    {"dining", "shopping", "entertainment", "subscriptions", "travel", "personal_care", "gifts"}
)
OTHER_EXPENSE_CATEGORIES = frozenset({"bank_fees", "other_expense", "uncategorized"})
SAVINGS_ACCOUNT_TYPES = frozenset({"fixed_deposit"})

# Ordered keyword rules used only when a transaction arrives as 'uncategorized'.
KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rent", ("RENT", "LANDLORD", "PG ACCOMMODATION")),
    ("utilities", ("ELECTRICITY", "BESCOM", "WATER BILL", "GAS BILL", "BROADBAND", "MOBILE RECHARGE", "POSTPAID")),
    ("groceries", ("GROCER", "SUPERMART", "KIRANA", "BIGBASKET", "FRESH MART", "DMART")),
    ("transport", ("METRO", "FUEL", "PETROL", "CAB", "AUTO RIDE", "RAILWAY", "PARKING")),
    ("insurance", ("INSURANCE", "PREMIUM")),
    ("healthcare", ("PHARMA", "CLINIC", "HOSPITAL", "DIAGNOSTIC", "MEDICAL")),
    ("education", ("SCHOOL", "TUITION", "COLLEGE", "COURSE FEE")),
    ("loan_emi", ("EMI", "LOAN REPAY")),
    ("subscriptions", ("SUBSCRIPTION", "STREAMING", "MEMBERSHIP", "MUSIC PLAN", "CLOUD STORAGE")),
    ("dining", ("RESTAURANT", "CAFE", "FOOD DELIVERY", "BISTRO", "DHABA")),
    ("entertainment", ("CINEMA", "MOVIE", "CONCERT", "GAMING")),
    ("travel", ("AIRLINE", "HOTEL", "HOLIDAY", "FLIGHT")),
    ("shopping", ("FASHION", "ELECTRONICS", "ONLINE STORE", "MALL", "APPAREL")),
    ("personal_care", ("SALON", "SPA", "GYM")),
)

Flow = Literal["income", "expense", "refund", "excluded"]
ExclusionReason = Literal[
    "internal_transfer", "unmatched_transfer", "probable_duplicate", "reversed", "reversal", "orphan_reversal"
]


@dataclass(frozen=True, slots=True)
class ClassifiedTxn:
    txn: TxnRecord
    flow: Flow
    category: str
    category_source: Literal["provided", "keyword_rule", "fallback"]
    category_group: Literal["income", "essential", "discretionary", "other", "transfer"]
    exclusion_reason: ExclusionReason | None = None
    is_savings_transfer: bool = False  # internal transfer into a savings/deposit account


_NON_ALNUM = re.compile(r"[^A-Z ]+")
_MULTI_SPACE = re.compile(r"\s+")


def normalize_merchant(merchant_name: str | None, description: str) -> str:
    """Stable merchant key: uppercase letters only, reference tokens removed."""
    source = merchant_name or description.split("/")[0]
    cleaned = _NON_ALNUM.sub(" ", source.upper())
    return _MULTI_SPACE.sub(" ", cleaned).strip() or "UNKNOWN"


def categorize(txn: TxnRecord) -> tuple[str, Literal["provided", "keyword_rule", "fallback"]]:
    if txn.category != "uncategorized":
        return txn.category, "provided"
    haystack = f"{txn.merchant_name or ''} {txn.description}".upper()
    for category, keywords in KEYWORD_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category, "keyword_rule"
    return "uncategorized", "fallback"


def category_group(category: str) -> Literal["income", "essential", "discretionary", "other", "transfer"]:
    if category in INCOME_CATEGORIES:
        return "income"
    if category in ESSENTIAL_CATEGORIES:
        return "essential"
    if category in DISCRETIONARY_CATEGORIES:
        return "discretionary"
    if category == "transfer":
        return "transfer"
    return "other"


def _duplicate_key(txn: TxnRecord) -> tuple[str, object, Decimal, str, str]:
    return (txn.account_id, txn.posted_on, txn.amount, txn.direction, txn.description.strip().upper())


def classify_transactions(
    transactions: list[TxnRecord], accounts: list[AccountRecord] | None = None
) -> list[ClassifiedTxn]:
    """Classify transactions deterministically (input order does not matter)."""
    account_types = {a.id: a.account_type for a in (accounts or [])}
    ordered = sorted(transactions, key=lambda t: (t.posted_on, t.external_ref, t.id))

    # 1. Probable duplicate imports: identical account/date/amount/direction/description.
    seen: set[tuple[str, object, Decimal, str, str]] = set()
    duplicates: set[str] = set()
    for txn in ordered:
        key = _duplicate_key(txn)
        if key in seen:
            duplicates.add(txn.id)
        else:
            seen.add(key)

    # 2. Reversal pairs: both the reversal and the original are neutralised.
    ids = {t.id for t in ordered if t.id not in duplicates}
    reversed_ids: set[str] = set()
    orphan_reversals: set[str] = set()
    for txn in ordered:
        if txn.transaction_type == "reversal" and txn.id not in duplicates:
            if txn.reverses_transaction_id and txn.reverses_transaction_id in ids:
                reversed_ids.add(txn.reverses_transaction_id)
            else:
                orphan_reversals.add(txn.id)

    # 3. Transfers: matched only when a group has an equal-amount debit and credit leg.
    legs: dict[str, list[TxnRecord]] = defaultdict(list)
    for txn in ordered:
        if txn.transaction_type in TRANSFER_TYPES and txn.transfer_group_id and txn.id not in duplicates:
            legs[txn.transfer_group_id].append(txn)
    matched_groups = {
        group
        for group, group_legs in legs.items()
        if any(o.direction == "debit" for o in group_legs)
        and any(i.direction == "credit" for i in group_legs)
        and sum((leg.signed_amount for leg in group_legs), Decimal("0")) == 0
    }

    results: list[ClassifiedTxn] = []
    for txn in ordered:
        category, source = categorize(txn)
        group = category_group(category)
        reason: ExclusionReason | None = None
        flow: Flow
        savings_transfer = False

        if txn.id in duplicates:
            flow, reason = "excluded", "probable_duplicate"
        elif txn.transaction_type == "reversal":
            flow, reason = "excluded", ("orphan_reversal" if txn.id in orphan_reversals else "reversal")
        elif txn.id in reversed_ids:
            flow, reason = "excluded", "reversed"
        elif txn.transaction_type in TRANSFER_TYPES:
            matched = txn.transfer_group_id in matched_groups
            flow, reason = "excluded", ("internal_transfer" if matched else "unmatched_transfer")
            group = "transfer"
            savings_transfer = (
                matched and txn.direction == "credit" and account_types.get(txn.account_id) in SAVINGS_ACCOUNT_TYPES
            )
        elif txn.transaction_type in INCOME_TYPES:
            flow = "income"
        elif txn.transaction_type == "refund":
            flow = "refund"
        elif txn.transaction_type in EXPENSE_TYPES:
            flow = "expense"
        else:  # pragma: no cover - guarded by DB check constraints
            flow, reason = "excluded", "unmatched_transfer"

        results.append(
            ClassifiedTxn(
                txn=txn,
                flow=flow,
                category=category,
                category_source=source,
                category_group=group,
                exclusion_reason=reason,
                is_savings_transfer=savings_transfer,
            )
        )
    return results
