"""Validate a synthetic dataset for structural and financial consistency.

Errors   = invalid records (would violate the schema or break analytics).
Warnings = deliberate edge cases worth knowing about (duplicates, stale data, ...).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from app.synthetic_data.generator import DEMO_EMAIL_DOMAIN, SyntheticDataset
from app.utils.dates import months_between

CREDIT_TYPES = {"salary", "business_income", "pension", "interest", "other_income", "transfer_in", "refund", "reversal"}
DEBIT_TYPES = {"purchase", "bill_payment", "loan_payment", "fee", "transfer_out", "reversal"}
MASK_PATTERN = re.compile(r"^XXXX\d{4}$")
LONG_DIGITS = re.compile(r"\d{9,}")  # anything resembling a real account/card number


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_dataset(ds: SyntheticDataset, min_customers: int = 50, min_history_months: int = 12) -> ValidationReport:
    report = ValidationReport()
    err, warn = report.errors.append, report.warnings.append
    profiles = {p["id"]: p for p in ds.profiles}
    customers = [p for p in ds.profiles if p["role"] == "customer"]
    accounts = {a["id"]: a for a in ds.accounts}
    txns = {t["id"]: t for t in ds.transactions}
    report.stats = {
        "customers": len(customers),
        "accounts": len(ds.accounts),
        "transactions": len(ds.transactions),
        "goals": len(ds.goals),
        "obligations": len(ds.obligations),
    }

    if len(customers) < min_customers:
        err(f"Only {len(customers)} customers; at least {min_customers} required")
    for p in ds.profiles:
        if not p["is_synthetic"]:
            err(f"Profile {p['id']} is not flagged synthetic")
        if p["email"] and not p["email"].endswith("@" + DEMO_EMAIL_DOMAIN):
            err(f"Profile {p['id']} email is outside the reserved demo domain")
    if len({p["email"] for p in ds.profiles}) != len(ds.profiles):
        err("Duplicate profile emails")
    fin_ids = {f["customer_id"] for f in ds.financial_profiles}
    for c in customers:
        if c["id"] not in fin_ids:
            err(f"Customer {c['id']} has no financial profile")

    masked_seen: set[tuple[object, str]] = set()
    for a in ds.accounts:
        if a["customer_id"] not in profiles:
            err(f"Account {a['id']} references unknown customer")
        if not MASK_PATTERN.match(a["masked_number"]):
            err(f"Account {a['id']} masked number has an invalid format")
        key = (a["customer_id"], a["masked_number"])
        if key in masked_seen:
            err(f"Account {a['id']} duplicates a masked number for the same customer")
        masked_seen.add(key)
        if (a["current_balance"] is None) != (a["balance_as_of"] is None):
            err(f"Account {a['id']} balance/as-of mismatch")

    refs: Counter[tuple[object, str]] = Counter()
    groups: dict[object, list[dict]] = defaultdict(list)
    for t in ds.transactions:
        account = accounts.get(t["account_id"])
        if account is None:
            err(f"Transaction {t['id']} references unknown account")
            continue
        if account["customer_id"] != t["customer_id"]:
            err(f"Transaction {t['id']} customer does not own its account")
        refs[(t["account_id"], t["external_ref"])] += 1
        if t["amount"] <= 0 or t["amount"] != t["amount"].quantize(Decimal("0.01")):
            err(f"Transaction {t['id']} has an invalid amount")
        allowed = CREDIT_TYPES if t["direction"] == "credit" else DEBIT_TYPES
        if t["transaction_type"] not in allowed:
            err(f"Transaction {t['id']} type does not match direction")
        if t["posted_on"] > ds.as_of or t["posted_on"] < account["opening_balance_date"]:
            err(f"Transaction {t['id']} is dated outside the account history")
        if LONG_DIGITS.search(t["description"]):
            err(f"Transaction {t['id']} description contains an account-number-like digit run")
        if t["transaction_type"] in {"transfer_in", "transfer_out"}:
            if t["transfer_group_id"] is None:
                err(f"Transfer {t['id']} has no transfer group")
            else:
                groups[t["transfer_group_id"]].append(t)
        if t["transaction_type"] == "reversal":
            original = txns.get(t["reverses_transaction_id"])
            if original is None:
                warn(f"Reversal {t['id']} has no matching original")
            elif original["customer_id"] != t["customer_id"] or original["amount"] != t["amount"]:
                err(f"Reversal {t['id']} does not match its original")
    duplicate_refs = [k for k, n in refs.items() if n > 1]
    if duplicate_refs:
        err(f"{len(duplicate_refs)} duplicate (account, external_ref) pairs")

    for group, legs in groups.items():
        total = sum((leg["amount"] if leg["direction"] == "credit" else -leg["amount"] for leg in legs), Decimal(0))
        if len(legs) != 2 or total != 0:
            err(f"Transfer group {group} is unbalanced")

    # Balance reconciliation: current = opening + signed non-duplicate transactions.
    dup_ids = {t["id"] for t in ds.transactions if str(t["external_ref"]).endswith("-DUP")}
    if dup_ids:
        warn(f"{len(dup_ids)} deliberate duplicate imports (excluded by analytics)")
    sums: dict[object, Decimal] = defaultdict(lambda: Decimal(0))
    for t in ds.transactions:
        if t["id"] not in dup_ids:
            sums[t["account_id"]] += t["amount"] if t["direction"] == "credit" else -t["amount"]
    for a in ds.accounts:
        if a["current_balance"] is None:
            continue
        expected = a["opening_balance"] + sums[a["id"]]
        if expected != a["current_balance"]:
            err(f"Account {a['id']} balance does not reconcile ({expected} vs {a['current_balance']})")
        if a["is_liquid"] and a["current_balance"] < 0:
            err(f"Liquid account {a['id']} has a negative balance")

    # History length per customer (new-to-bank personas are expected to be short).
    segments = {f["customer_id"]: f["persona_segment"] for f in ds.financial_profiles}
    by_customer: dict[object, list] = defaultdict(list)
    for t in ds.transactions:
        by_customer[t["customer_id"]].append(t["posted_on"])
    short = 0
    for c in customers:
        dates = by_customer.get(c["id"], [])
        if not dates:
            err(f"Customer {c['id']} has no transactions")
            continue
        span = months_between(min(dates), max(dates))
        if span < min_history_months - 1 and segments.get(c["id"]) not in {"new_to_bank", "stale_profile"}:
            err(f"Customer {c['id']} has only {span} months of history")
        if segments.get(c["id"]) == "new_to_bank":
            short += 1
    if short:
        warn(f"{short} new-to-bank customers intentionally have short histories")

    for g in ds.goals:
        if g["customer_id"] not in profiles:
            err(f"Goal {g['id']} references unknown customer")
        if g["target_amount"] <= 0 or g["saved_amount"] < 0:
            err(f"Goal {g['id']} has invalid amounts")
        if g["saved_amount"] > g["target_amount"] and g["status"] != "achieved":
            err(f"Goal {g['id']} saved more than target but not achieved")
    for o in ds.obligations:
        if o["customer_id"] not in profiles:
            err(f"Obligation {o['id']} references unknown customer")
        if o["amount"] <= 0:
            err(f"Obligation {o['id']} has a non-positive amount")
        if o["end_date"] is not None and o["end_date"] < o["next_due_date"]:
            err(f"Obligation {o['id']} ends before it is due")

    missing_income = sum(1 for f in ds.financial_profiles if f["declared_monthly_income"] is None)
    missing_balance = sum(1 for a in ds.accounts if a["current_balance"] is None)
    if missing_income:
        warn(f"{missing_income} customers deliberately lack declared income")
    if missing_balance:
        warn(f"{missing_balance} accounts deliberately lack a reported balance")
    return report
