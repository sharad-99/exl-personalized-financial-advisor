"""Reproducible synthetic data generator.

ALL DATA PRODUCED HERE IS FABRICATED. Names, employers, merchants, references
and amounts are invented; masked account numbers are random 4-digit suffixes
and are not real account numbers. Never present this as real bank data.

Determinism: identical (seed, as_of, customer_count, history_months) inputs
produce byte-identical output. IDs are UUIDv5 values derived from the seed.
Amounts are generated as integer paise (no floating-point money).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from app.models.domain import (
    AccountRecord,
    CustomerFinancialData,
    FinancialProfileRecord,
    GoalRecord,
    ObligationRecord,
    TxnRecord,
)
from app.utils.dates import add_months, month_start
from app.utils.money import from_paise

GENERATOR_VERSION = "1.0.0"
DEMO_EMAIL_DOMAIN = "demo.exl.test"  # .test is reserved and can never receive mail
ID_NAMESPACE = uuid.UUID("7d6f1c2e-5a8b-4f3e-9c1d-2b4a6e8f0a13")

FIRST_NAMES = [
    "Aarav",
    "Diya",
    "Vihaan",
    "Ananya",
    "Arjun",
    "Ishita",
    "Kabir",
    "Meera",
    "Rohan",
    "Saanvi",
    "Aditya",
    "Kavya",
    "Reyansh",
    "Nisha",
    "Vivaan",
    "Pooja",
    "Kunal",
    "Tara",
    "Siddharth",
    "Riya",
    "Farhan",
    "Neha",
    "Dev",
    "Zoya",
    "Harsh",
    "Lakshmi",
    "Manav",
    "Priya",
    "Yash",
    "Aisha",
]
LAST_NAMES = [
    "Sharma",
    "Iyer",
    "Mehta",
    "Reddy",
    "Kulkarni",
    "Banerjee",
    "Nair",
    "Gupta",
    "Singh",
    "Desai",
    "Khan",
    "Pillai",
    "Joshi",
    "Chatterjee",
    "Rao",
    "Menon",
    "Verma",
    "Bose",
    "Patel",
    "Kapoor",
]
EMPLOYERS = [
    "Northwind Technologies",
    "Lotus Retail Services",
    "Indigo Logistics",
    "Banyan Healthcare",
    "Sahyadri Engineering",
    "Monsoon Media Labs",
    "Peacock Financial Ops",
    "Ganga Textiles",
]
GIG_CLIENTS = [
    "FreelanceHub Payout",
    "DesignDesk Client",
    "RideShare Earnings",
    "TutorConnect Payout",
    "CraftBazaar Sales",
    "CodeSprint Contract",
]

SUBSCRIPTIONS = [
    ("StreamFlix", 64900),
    ("TuneBox Music Plan", 11900),
    ("CloudVault Storage", 7500),
    ("FitLife Gym Membership", 149900),
    ("NewsDaily Digital", 19900),
    ("PlayArena Gaming Pass", 49900),
    ("LearnLoop Courses", 89900),
]
MERCHANTS: dict[str, list[str]] = {
    "groceries": ["FreshMart Grocers", "Daily Basket Kirana", "GreenLeaf Supermart"],
    "transport": ["CityMetro Card", "QuickCab Rides", "HighwayFuel Petrol"],
    "dining": ["Cafe Aroma", "QuickBite Food Delivery", "Spice Route Restaurant", "Bistro 21"],
    "shopping": ["UrbanThread Fashion", "GadgetHub Electronics", "MegaCart Online Store"],
    "entertainment": ["SilverScreen Cinema", "LiveBeat Concerts"],
    "travel": ["SkyWay Airline", "Coastal Stay Hotel", "Wanderlust Holidays"],
    "healthcare": ["CarePlus Pharma", "Wellness Clinic", "Precision Diagnostic"],
    "personal_care": ["Glow Salon", "Serene Spa"],
    "gifts": ["GiftBox Store", "Seva Foundation Donation"],
}


@dataclass(frozen=True)
class PersonaSpec:
    segment: str
    count: int
    income_pattern: str
    income_range: tuple[int, int]  # monthly, rupees
    essential_ratio: tuple[float, float]  # share of income
    discretionary_ratio: tuple[float, float]
    liquid_months: tuple[float, float]  # ending liquid balance in months of essential spend
    age_bands: tuple[str, ...]
    dependents: tuple[int, int]
    has_loan: float = 0.0
    has_card: float = 0.5
    saves_to_deposit: float = 0.3
    history_months: int | None = None
    stale_days: tuple[int, int] | None = None


PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        "young_salaried",
        10,
        "salaried_stable",
        (35_000, 90_000),
        (0.35, 0.50),
        (0.15, 0.25),
        (0.5, 3.0),
        ("18-24", "25-34"),
        (0, 0),
        has_loan=0.2,
        has_card=0.7,
        saves_to_deposit=0.6,
    ),
    PersonaSpec(
        "family_goal_saver",
        10,
        "salaried_stable",
        (80_000, 220_000),
        (0.40, 0.55),
        (0.08, 0.15),
        (3.5, 9.0),
        ("35-44", "45-54"),
        (1, 3),
        has_loan=0.5,
        has_card=0.6,
        saves_to_deposit=0.9,
    ),
    PersonaSpec(
        "pre_retiree",
        7,
        "salaried_stable",
        (90_000, 250_000),
        (0.30, 0.45),
        (0.08, 0.15),
        (6.0, 14.0),
        ("55-64",),
        (0, 1),
        has_loan=0.1,
        has_card=0.5,
        saves_to_deposit=0.9,
    ),
    PersonaSpec(
        "gig_worker",
        7,
        "irregular",
        (25_000, 80_000),
        (0.55, 0.70),
        (0.15, 0.25),
        (0.3, 2.5),
        ("25-34", "35-44"),
        (0, 2),
        has_loan=0.2,
        has_card=0.3,
        saves_to_deposit=0.1,
    ),
    PersonaSpec(
        "high_spender",
        7,
        "salaried_stable",
        (70_000, 180_000),
        (0.30, 0.40),
        (0.48, 0.62),
        (0.4, 2.0),
        ("25-34", "35-44"),
        (0, 1),
        has_loan=0.2,
        has_card=1.0,
        saves_to_deposit=0.0,
    ),
    PersonaSpec(
        "debt_stressed",
        7,
        "salaried_stable",
        (40_000, 110_000),
        (0.66, 0.80),
        (0.14, 0.22),
        (0.1, 0.9),
        ("25-34", "35-44", "45-54"),
        (0, 3),
        has_loan=1.0,
        has_card=0.8,
        saves_to_deposit=0.0,
    ),
    PersonaSpec(
        "new_to_bank",
        5,
        "salaried_stable",
        (30_000, 70_000),
        (0.40, 0.55),
        (0.12, 0.22),
        (0.5, 2.0),
        ("18-24", "25-34"),
        (0, 0),
        has_card=0.2,
        history_months=2,
    ),
    PersonaSpec(
        "stale_profile",
        7,
        "unknown",
        (30_000, 120_000),
        (0.40, 0.55),
        (0.10, 0.20),
        (1.0, 4.0),
        ("35-44", "45-54", "65+"),
        (0, 2),
        has_loan=0.3,
        has_card=0.3,
        stale_days=(50, 130),
    ),
)


@dataclass
class SyntheticDataset:
    seed: int
    as_of: date
    generator_version: str = GENERATOR_VERSION
    profiles: list[dict[str, Any]] = field(default_factory=list)
    financial_profiles: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    obligations: list[dict[str, Any]] = field(default_factory=list)

    def customer_ids(self) -> list[uuid.UUID]:
        return [p["id"] for p in self.profiles if p["role"] == "customer"]


class _CustomerBuilder:
    """Builds one customer's records with its own deterministic RNG."""

    def __init__(self, dataset: SyntheticDataset, index: int, spec: PersonaSpec, history_months: int) -> None:
        self.ds = dataset
        self.index = index
        self.spec = spec
        self.rng = random.Random(f"{dataset.seed}:customer:{index}")
        self.as_of = dataset.as_of
        months = spec.history_months or history_months
        self.start = (
            add_months(month_start(self.as_of), -(months - 1))
            if spec.history_months
            else add_months(month_start(self.as_of), -months)
        )
        self.end = self.as_of
        if spec.stale_days:
            self.end = self.as_of - timedelta(days=self.rng.randint(*spec.stale_days))
        self.customer_id = self._id("profile")
        self.txns: list[dict[str, Any]] = []
        self.ref_counter = 0

    # -- helpers -------------------------------------------------------------
    def _id(self, *parts: object) -> uuid.UUID:
        return uuid.uuid5(ID_NAMESPACE, f"{self.ds.seed}:{self.index}:" + ":".join(map(str, parts)))

    def _paise(self, low_rupees: float, high_rupees: float) -> int:
        return self.rng.randint(int(low_rupees * 100), int(high_rupees * 100))

    def _ref(self) -> str:
        self.ref_counter += 1
        return f"SYN{self.index:03d}{self.ref_counter:05d}"

    def _day(self, month: date, low: int, high: int) -> date | None:
        day = month.replace(day=min(self.rng.randint(low, high), 28))
        if day < self.start or day > self.end:
            return None
        return day

    def _add(
        self,
        account: uuid.UUID,
        posted_on: date | None,
        paise: int,
        direction: str,
        ttype: str,
        category: str,
        description: str,
        merchant: str | None = None,
        transfer_group: uuid.UUID | None = None,
        reverses: uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        if posted_on is None or paise <= 0:
            return None
        ref = self._ref()
        row = {
            "id": self._id("txn", ref),
            "account_id": account,
            "customer_id": self.customer_id,
            "external_ref": ref,
            "posted_on": posted_on,
            "amount": from_paise(paise),
            "direction": direction,
            "transaction_type": ttype,
            "category": category,
            "merchant_name": merchant,
            "description": description[:200],
            "transfer_group_id": transfer_group,
            "reverses_transaction_id": reverses,
        }
        self.txns.append(row)
        return row

    def _upi(self, merchant: str) -> str:
        return f"UPI/{merchant.upper()}/{self.rng.randint(100000, 999999)}"

    # -- build ---------------------------------------------------------------
    def build(self) -> None:
        spec, rng = self.spec, self.rng
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        income = rng.randrange(spec.income_range[0], spec.income_range[1], 500)
        essential_ratio = rng.uniform(*spec.essential_ratio)
        discretionary_ratio = rng.uniform(*spec.discretionary_ratio)
        dependents = rng.randint(*spec.dependents)
        is_stale = spec.stale_days is not None
        missing_income = is_stale and self.index % 2 == 0
        missing_balance = is_stale and self.index % 3 == 0

        created = datetime.combine(self.start - timedelta(days=30), time(9, 0), tzinfo=UTC)
        profile_updated = (
            created
            if is_stale
            else datetime.combine(self.as_of - timedelta(days=rng.randint(5, 200)), time(10, 0), tzinfo=UTC)
        )
        email = f"customer{self.index:02d}@{DEMO_EMAIL_DOMAIN}"
        self.ds.profiles.append(
            {
                "id": self.customer_id,
                "auth_user_id": self._id("auth"),
                "role": "customer",
                "display_name": f"{first} {last}",
                "email": email,
                "is_synthetic": True,
                "data_sharing_consent": True,
                "marketing_consent": rng.random() < 0.3,
                "consent_updated_at": created,
                "created_at": created,
            }
        )
        income_pattern = spec.income_pattern
        if spec.segment == "pre_retiree" and rng.random() < 0.3:
            income_pattern = "pension"
        self.ds.financial_profiles.append(
            {
                "customer_id": self.customer_id,
                "persona_segment": spec.segment,
                "income_pattern": income_pattern,
                "declared_monthly_income": None if missing_income else Decimal(income).quantize(Decimal("0.01")),
                "age_band": rng.choice(spec.age_bands),
                "dependents": dependents,
                "city_tier": rng.choice(["tier_1", "tier_1", "tier_2", "tier_3"]),
                "risk_preference": rng.choice(["conservative", "balanced", "growth", "unknown"]),
                "currency": "INR",
                "profile_updated_at": profile_updated,
                "created_at": created,
            }
        )

        savings = self._id("account", "savings")
        card = self._id("account", "card") if rng.random() < spec.has_card else None
        deposit = self._id("account", "deposit") if rng.random() < spec.saves_to_deposit else None
        accounts: list[tuple[uuid.UUID, str, str, bool]] = [(savings, "savings", "Primary Savings", True)]
        if card:
            accounts.append((card, "credit_card", "Rewards Credit Card", False))
        if deposit:
            accounts.append((deposit, "fixed_deposit", "Recurring Deposit", False))

        employer = rng.choice(EMPLOYERS)
        subs = rng.sample(SUBSCRIPTIONS, k=rng.randint(4, 6) if spec.segment == "high_spender" else rng.randint(0, 3))
        rent = (
            int(income * rng.uniform(0.18, 0.28)) * 100
            if spec.segment not in {"pre_retiree"} and rng.random() < 0.65
            else 0
        )
        loan_emi = (
            int(income * rng.uniform(0.15, 0.32 if spec.segment == "debt_stressed" else 0.18)) * 100
            if rng.random() < spec.has_loan
            else 0
        )
        insurance_annual = rng.randrange(12_000, 45_000, 500) * 100 if rng.random() < 0.6 else 0
        insurance_due = (
            self.as_of + timedelta(days=rng.randint(3, 25))
            if rng.random() < 0.5
            else self.as_of + timedelta(days=rng.randint(40, 300))
        )
        school_fee_quarterly = (
            rng.randrange(15_000, 60_000, 1000) * 100
            if dependents and spec.segment in {"family_goal_saver", "debt_stressed"}
            else 0
        )
        # Savers keep a small monthly buffer and auto-sweep the rest to the recurring deposit.
        self.retain = int(income * rng.uniform(0.02, 0.12)) * 100

        essential_budget = int(income * essential_ratio) * 100 - rent - loan_emi
        discretionary_budget = int(income * discretionary_ratio) * 100
        subs_total = sum(price for _, price in subs)

        month = month_start(self.start)
        while month <= self.end:
            self._month(
                month,
                savings,
                card,
                deposit,
                income,
                employer,
                subs,
                rent,
                loan_emi,
                max(essential_budget, 600_000),
                max(discretionary_budget - subs_total, 200_000),
                school_fee_quarterly,
                insurance_annual,
                insurance_due,
            )
            month = add_months(month, 1)

        self._edge_cases(savings)
        self._finalise_accounts(accounts, savings, income, essential_ratio, missing_balance)
        self._goals(income, spec.segment)
        self._obligations(rent, loan_emi, insurance_annual, insurance_due, school_fee_quarterly, card)

    def _month(
        self,
        month: date,
        savings: uuid.UUID,
        card: uuid.UUID | None,
        deposit: uuid.UUID | None,
        income: int,
        employer: str,
        subs: list[tuple[str, int]],
        rent: int,
        loan_emi: int,
        essential_budget: int,
        discretionary_budget: int,
        school_fee: int,
        insurance_annual: int,
        insurance_due: date,
    ) -> None:
        rng, spec = self.rng, self.spec
        # Income
        if spec.income_pattern == "irregular":
            total = int(income * rng.choice([0.35, 0.6, 0.9, 1.0, 1.2, 1.5, 1.8])) * 100
            parts = rng.randint(2, 6)
            for _ in range(parts):
                client = rng.choice(GIG_CLIENTS)
                self._add(
                    savings,
                    self._day(month, 1, 28),
                    total // parts,
                    "credit",
                    "business_income",
                    "business_income",
                    f"NEFT/{client.upper()}/{rng.randint(1000, 9999)}",
                    client,
                )
        else:
            hike = (
                1.08 if month.month >= 4 and month.year == self.as_of.year and month.month <= self.as_of.month else 1.0
            )
            ttype = "pension" if self.ds.financial_profiles[-1]["income_pattern"] == "pension" else "salary"
            self._add(
                savings,
                self._day(month, 1, 1),
                int(income * hike) * 100,
                "credit",
                ttype,
                ttype,
                f"NEFT/SALARY/{employer.upper()}",
                employer,
            )
        if month.month in (3, 6, 9, 12):
            self._add(
                savings,
                self._day(month, 28, 28),
                self._paise(80, 900),
                "credit",
                "interest",
                "interest",
                "INT.CREDIT/SAVINGS INTEREST",
                "Savings Interest",
            )

        # Fixed essentials
        if rent:
            self._add(
                savings,
                self._day(month, 3, 5),
                rent,
                "debit",
                "bill_payment",
                "rent",
                "IMPS/RENT/LANDLORD PAYMENT",
                "Landlord Rent",
            )
        if loan_emi:
            self._add(
                savings,
                self._day(month, 5, 5),
                loan_emi,
                "debit",
                "loan_payment",
                "loan_emi",
                "ACH/EMI/HOMESTEAD FINANCE LOAN",
                "Homestead Finance EMI",
            )
        self._add(
            savings,
            self._day(month, 8, 12),
            self._paise(900, 3200),
            "debit",
            "bill_payment",
            "utilities",
            "BBPS/ELECTRICITY/CITY POWER",
            "City Power Electricity",
        )
        self._add(
            savings,
            self._day(month, 10, 10),
            99_900,
            "debit",
            "bill_payment",
            "utilities",
            "BBPS/BROADBAND/FIBERNET",
            "FiberNet Broadband",
        )
        if school_fee and month.month in (1, 4, 7, 10):
            self._add(
                savings,
                self._day(month, 6, 10),
                school_fee,
                "debit",
                "bill_payment",
                "education",
                "NEFT/SCHOOL FEES/BRIGHT FUTURE SCHOOL",
                "Bright Future School",
            )
        previous_premium = add_months(insurance_due, -12)  # last year's payment falls inside the history
        if insurance_annual and month == month_start(previous_premium):
            self._add(
                savings,
                self._day(month, previous_premium.day, previous_premium.day),
                insurance_annual,
                "debit",
                "bill_payment",
                "insurance",
                "ACH/INSURANCE PREMIUM/SHIELD LIFE",
                "Shield Life Insurance",
            )

        # Variable essentials (groceries, transport, healthcare)
        variable = essential_budget
        for category, share, count in (("groceries", 0.55, 5), ("transport", 0.3, 6), ("healthcare", 0.15, 1)):
            pot = int(variable * share * rng.uniform(0.85, 1.15))
            for _ in range(count):
                merchant = rng.choice(MERCHANTS[category])
                category_out = category
                if rng.random() < 0.04:  # some arrive uncategorised (keyword rules recover most)
                    category_out = "uncategorized"
                self._add(
                    savings,
                    self._day(month, 1, 28),
                    pot // count,
                    "debit",
                    "purchase",
                    category_out,
                    self._upi(merchant),
                    merchant,
                )

        # Subscriptions (fixed day, fixed amount -> detected as recurring)
        for name, price in subs:
            account = card or savings
            self._add(
                account,
                self._day(month, 14, 14),
                price,
                "debit",
                "purchase",
                "subscriptions",
                f"CARD/{name.upper()}/SUBSCRIPTION",
                name,
            )

        # Discretionary spend; high spenders spike in festive months (Oct/Nov) and recent months
        spike = 1.0
        if spec.segment == "high_spender" and (month.month in (10, 11) or month >= add_months(self.as_of, -2)):
            spike = rng.uniform(1.3, 1.6)
        pot = int(discretionary_budget * spike * rng.uniform(0.8, 1.2))
        weights = {
            "dining": 0.35,
            "shopping": 0.3,
            "entertainment": 0.12,
            "travel": 0.13,
            "personal_care": 0.05,
            "gifts": 0.05,
        }
        for category, share in weights.items():
            n = max(1, int(share * 10))
            amount = int(pot * share)
            for _ in range(n):
                merchant = rng.choice(MERCHANTS[category])
                account = card if card and category in {"dining", "shopping", "travel"} else savings
                self._add(
                    account,
                    self._day(month, 1, 28),
                    amount // n,
                    "debit",
                    "purchase",
                    category,
                    f"POS/{merchant.upper()}/{rng.randint(1000, 9999)}",
                    merchant,
                )
        if rng.random() < 0.05:
            self._add(
                savings,
                self._day(month, 20, 26),
                self._paise(200, 600),
                "debit",
                "fee",
                "bank_fees",
                "CHG/SMS ALERT CHARGES",
                "Bank Charges",
            )

        # Pay last month's card spend in full via an internal transfer (no double counting)
        if card:
            prev_start = add_months(month, -1)
            owed = sum(
                int(t["amount"] * 100)
                for t in self.txns
                if t["account_id"] == card and t["direction"] == "debit" and prev_start <= t["posted_on"] < month
            )
            refunds = sum(
                int(t["amount"] * 100)
                for t in self.txns
                if t["account_id"] == card
                and t["direction"] == "credit"
                and t["transaction_type"] != "transfer_in"
                and prev_start <= t["posted_on"] < month
            )
            due = owed - refunds
            day = self._day(month, 18, 18)
            if due > 0 and day:
                group = self._id("transfer", "card", month.isoformat())
                self._add(
                    savings,
                    day,
                    due,
                    "debit",
                    "transfer_out",
                    "transfer",
                    "IMPS/CARD BILL PAYMENT",
                    "Card Bill Payment",
                    transfer_group=group,
                )
                self._add(
                    card,
                    day,
                    due,
                    "credit",
                    "transfer_in",
                    "transfer",
                    "PAYMENT RECEIVED - THANK YOU",
                    "Card Bill Payment",
                    transfer_group=group,
                )

        # Month-end auto-sweep of surplus into the recurring deposit (internal transfer)
        sweep_day = self._day(month, 27, 27)
        if deposit and sweep_day:
            next_month = add_months(month, 1)
            month_net = sum(
                int(t["amount"] * 100) * (1 if t["direction"] == "credit" else -1)
                for t in self.txns
                if t["account_id"] == savings and month <= t["posted_on"] < next_month
            )
            sweep = (month_net - self.retain) // 10_000 * 10_000  # whole hundreds of rupees
            if sweep >= 100_000:
                group = self._id("transfer", "deposit", month.isoformat())
                self._add(
                    savings,
                    sweep_day,
                    sweep,
                    "debit",
                    "transfer_out",
                    "transfer",
                    "IMPS/TRANSFER/SELF RECURRING DEPOSIT",
                    "Self Transfer",
                    transfer_group=group,
                )
                self._add(
                    deposit,
                    sweep_day,
                    sweep,
                    "credit",
                    "transfer_in",
                    "transfer",
                    "IMPS/TRANSFER/FROM SAVINGS",
                    "Self Transfer",
                    transfer_group=group,
                )

    def _edge_cases(self, savings: uuid.UUID) -> None:
        """Inject realistic data-quality edge cases for a subset of customers."""
        rng = self.rng
        purchases = [t for t in self.txns if t["transaction_type"] == "purchase" and t["account_id"] == savings]
        if not purchases:
            return
        if self.index % 4 == 0:  # refund of a shopping purchase
            original = rng.choice(purchases)
            self._add(
                savings,
                min(original["posted_on"] + timedelta(days=5), self.end),
                int(original["amount"] * 100),
                "credit",
                "refund",
                original["category"],
                f"REFUND/{(original['merchant_name'] or 'MERCHANT').upper()}",
                original["merchant_name"],
            )
        if self.index % 5 == 0:  # failed payment reversed by the bank
            original = rng.choice(purchases)
            self._add(
                savings,
                original["posted_on"],
                int(original["amount"] * 100),
                "credit",
                "reversal",
                original["category"],
                f"REVERSAL/{(original['merchant_name'] or 'MERCHANT').upper()}",
                original["merchant_name"],
                reverses=original["id"],
            )
        if self.index % 6 == 0:  # duplicate import of the same bank record
            for original in rng.sample(purchases, k=min(2, len(purchases))):
                dup = dict(original)
                self.ref_counter += 1
                dup["external_ref"] = f"{original['external_ref']}-DUP"
                dup["id"] = self._id("txn", dup["external_ref"])
                self.txns.append(dup)

    def _finalise_accounts(
        self,
        accounts: list[tuple[uuid.UUID, str, str, bool]],
        savings: uuid.UUID,
        income: int,
        essential_ratio: float,
        missing_balance: bool,
    ) -> None:
        rng = self.rng
        duplicate_ids = {t["id"] for t in self.txns if str(t["external_ref"]).endswith("-DUP")}
        for account_id, account_type, nickname, liquid in accounts:
            rows = sorted(
                (t for t in self.txns if t["account_id"] == account_id and t["id"] not in duplicate_ids),
                key=lambda t: (t["posted_on"], t["external_ref"]),
            )
            running, low = 0, 0
            for t in rows:
                running += int(t["amount"] * 100) * (1 if t["direction"] == "credit" else -1)
                low = min(low, running)
            net = running
            if account_type == "savings":
                target_end = int(income * essential_ratio * rng.uniform(*self.spec.liquid_months)) * 100
                opening = target_end - net
                opening = max(opening, -low + 50_000)  # never let the running balance go below Rs 500
            elif account_type == "fixed_deposit":
                opening = rng.randrange(20_000, 400_000, 1000) * 100
            else:  # credit card starts with nothing owed; negative balance = amount owed
                opening = 0
            balance_known = not (missing_balance and account_type == "savings")
            as_of_dt = datetime.combine(self.end, time(23, 0), tzinfo=UTC)
            masked = f"XXXX{rng.randint(1000, 9999)}"
            self.ds.accounts.append(
                {
                    "id": account_id,
                    "customer_id": self.customer_id,
                    "account_type": account_type,
                    "nickname": nickname,
                    "masked_number": masked,
                    "currency": "INR",
                    "opening_balance": from_paise(opening),
                    "opening_balance_date": self.start,
                    "current_balance": from_paise(opening + net) if balance_known else None,
                    "balance_as_of": as_of_dt if balance_known else None,
                    "is_liquid": liquid,
                    "status": "active",
                }
            )
        self.ds.transactions.extend(sorted(self.txns, key=lambda t: (t["posted_on"], t["external_ref"])))

    def _goals(self, income: int, segment: str) -> None:
        rng = self.rng
        templates = {
            "young_salaried": [
                ("Emergency Fund", "emergency_fund", 3),
                ("Goa Trip", "travel", 0.8),
                ("First Car", "vehicle", 8),
            ],
            "family_goal_saver": [
                ("Child Education Fund", "education", 20),
                ("Home Down Payment", "home_purchase", 30),
                ("Family Emergency Fund", "emergency_fund", 6),
            ],
            "pre_retiree": [("Retirement Corpus Top-up", "retirement", 40), ("Medical Reserve", "emergency_fund", 6)],
            "gig_worker": [("Income Buffer", "emergency_fund", 6), ("New Laptop", "other", 1.5)],
            "high_spender": [("Europe Holiday", "travel", 4), ("Wedding Fund", "wedding", 12)],
            "debt_stressed": [("Clear Credit Card Debt", "debt_payoff", 2), ("Emergency Fund", "emergency_fund", 3)],
            "new_to_bank": [("Emergency Fund", "emergency_fund", 3)],
            "stale_profile": [("Home Renovation", "other", 6)],
        }[segment]
        count = rng.randint(1, len(templates)) if segment != "stale_profile" else rng.randint(0, 1)
        for position, (name, goal_type, multiple) in enumerate(templates[:count]):
            target = int(income * multiple / 1000) * 1000 * 100 or 1_000_000
            progress = rng.choice([0.1, 0.25, 0.45, 0.55, 0.8, 0.95, 1.0])
            saved = int(target * progress)
            months_out = rng.randint(4, 48)
            contribution = (
                None if rng.random() < 0.25 else int((target - saved) / months_out * rng.uniform(0.5, 1.3)) // 100 * 100
            )
            self.ds.goals.append(
                {
                    "id": self._id("goal", position),
                    "customer_id": self.customer_id,
                    "name": name,
                    "goal_type": goal_type,
                    "target_amount": from_paise(target),
                    "saved_amount": from_paise(saved),
                    "monthly_contribution": from_paise(contribution) if contribution is not None else None,
                    "target_date": add_months(self.as_of, months_out),
                    "priority": position + 1,
                    "status": "achieved" if saved >= target else "active",
                }
            )

    def _obligations(
        self,
        rent: int,
        loan_emi: int,
        insurance_annual: int,
        insurance_due: date,
        school_fee: int,
        card: uuid.UUID | None,
    ) -> None:
        rng = self.rng
        items: list[dict[str, Any]] = []

        def next_monthly(day: int) -> date:
            candidate = self.as_of.replace(day=day)
            return candidate if candidate >= self.as_of else add_months(candidate, 1)

        if rent:
            items.append(
                dict(
                    obligation_type="rent",
                    name="House Rent",
                    amount=rent,
                    frequency="monthly",
                    next_due_date=next_monthly(4),
                    is_essential=True,
                )
            )
        if loan_emi:
            items.append(
                dict(
                    obligation_type="loan_emi",
                    name="Home/Personal Loan EMI",
                    amount=loan_emi,
                    frequency="monthly",
                    next_due_date=next_monthly(5),
                    is_essential=True,
                    outstanding_principal=loan_emi * rng.randint(18, 120),
                    interest_rate_apr=Decimal(rng.choice(["9.25", "10.50", "12.75", "14.00", "16.50"])),
                    end_date=add_months(self.as_of, rng.randint(18, 120)),
                )
            )
        if insurance_annual:
            items.append(
                dict(
                    obligation_type="insurance_premium",
                    name="Life Insurance Premium",
                    amount=insurance_annual,
                    frequency="annual",
                    next_due_date=insurance_due,
                    is_essential=True,
                )
            )
        if school_fee:
            quarter_months = [1, 4, 7, 10]
            due_month = next(
                m
                for m in quarter_months + [13]
                if m > self.as_of.month or (m == self.as_of.month and self.as_of.day <= 8)
            )
            year = self.as_of.year + (1 if due_month == 13 else 0)
            items.append(
                dict(
                    obligation_type="school_fees",
                    name="School Fees",
                    amount=school_fee,
                    frequency="quarterly",
                    next_due_date=date(year, 1 if due_month == 13 else due_month, 8),
                    is_essential=True,
                )
            )
        if card:
            items.append(
                dict(
                    obligation_type="credit_card_bill",
                    name="Credit Card Bill (pay in full)",
                    amount=rng.randrange(5_000, 40_000, 500) * 100,
                    frequency="monthly",
                    next_due_date=next_monthly(18),
                    is_essential=True,
                )
            )
        if self.index % 7 == 3:
            items.append(
                dict(
                    obligation_type="tax",
                    name="Advance Tax Instalment",
                    amount=rng.randrange(10_000, 60_000, 1000) * 100,
                    frequency="one_time",
                    next_due_date=self.as_of + timedelta(days=rng.randint(10, 28)),
                    is_essential=True,
                )
            )
        for position, item in enumerate(items):
            principal = item.pop("outstanding_principal", None)
            self.ds.obligations.append(
                {
                    "id": self._id("obligation", position),
                    "customer_id": self.customer_id,
                    **{k: v for k, v in item.items() if k != "amount"},
                    "amount": from_paise(item["amount"]),
                    "outstanding_principal": from_paise(principal) if principal else None,
                    "interest_rate_apr": item.get("interest_rate_apr"),
                    "end_date": item.get("end_date"),
                    "status": "active",
                }
            )


def advisor_profile(seed: int) -> dict[str, Any]:
    return {
        "id": uuid.uuid5(ID_NAMESPACE, f"{seed}:advisor:profile"),
        "auth_user_id": uuid.uuid5(ID_NAMESPACE, f"{seed}:advisor:auth"),
        "role": "advisor",
        "display_name": "EXL Demo Analyst",
        "email": f"advisor@{DEMO_EMAIL_DOMAIN}",
        "is_synthetic": True,
        "data_sharing_consent": True,
        "marketing_consent": False,
        "consent_updated_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


def generate_dataset(
    seed: int = 42, as_of: date | None = None, history_months: int = 13, customer_count: int | None = None
) -> SyntheticDataset:
    """Generate the full synthetic dataset.

    customer_count, when given, must be >= 50 for full persona coverage; personas
    are repeated in order if more customers are requested.
    """
    if history_months < 12:
        raise ValueError("history_months must be at least 12")
    as_of = as_of or datetime.now(UTC).date()
    dataset = SyntheticDataset(seed=seed, as_of=as_of)
    dataset.profiles.append(advisor_profile(seed))
    specs = [spec for spec in PERSONAS for _ in range(spec.count)]
    total = customer_count or len(specs)
    for index in range(1, total + 1):
        spec = specs[(index - 1) % len(specs)]
        _CustomerBuilder(dataset, index, spec, history_months).build()
    return dataset


def customer_financial_data(dataset: SyntheticDataset, customer_id: uuid.UUID) -> CustomerFinancialData:
    """Convert dataset rows into the domain object used by analytics (no database needed)."""
    profile = next(p for p in dataset.profiles if p["id"] == customer_id)
    fin = next((f for f in dataset.financial_profiles if f["customer_id"] == customer_id), None)
    return CustomerFinancialData(
        customer_id=str(customer_id),
        profile=FinancialProfileRecord(
            persona_segment=fin["persona_segment"],
            income_pattern=fin["income_pattern"],
            declared_monthly_income=fin["declared_monthly_income"],
            age_band=fin["age_band"],
            dependents=fin["dependents"],
            risk_preference=fin["risk_preference"],
            profile_updated_at=fin["profile_updated_at"],
        )
        if fin
        else None,
        accounts=[
            AccountRecord(
                id=str(a["id"]),
                account_type=a["account_type"],
                nickname=a["nickname"],
                masked_number=a["masked_number"],
                opening_balance=a["opening_balance"],
                opening_balance_date=a["opening_balance_date"],
                current_balance=a["current_balance"],
                balance_as_of=a["balance_as_of"],
                is_liquid=a["is_liquid"],
                status=a["status"],
            )
            for a in dataset.accounts
            if a["customer_id"] == customer_id
        ],
        transactions=[
            TxnRecord(
                id=str(t["id"]),
                account_id=str(t["account_id"]),
                external_ref=t["external_ref"],
                posted_on=t["posted_on"],
                amount=t["amount"],
                direction=t["direction"],
                transaction_type=t["transaction_type"],
                category=t["category"],
                description=t["description"],
                merchant_name=t["merchant_name"],
                transfer_group_id=str(t["transfer_group_id"]) if t["transfer_group_id"] else None,
                reverses_transaction_id=str(t["reverses_transaction_id"]) if t["reverses_transaction_id"] else None,
            )
            for t in dataset.transactions
            if t["customer_id"] == customer_id
        ],
        goals=[
            GoalRecord(
                id=str(g["id"]),
                name=g["name"],
                goal_type=g["goal_type"],
                target_amount=g["target_amount"],
                saved_amount=g["saved_amount"],
                monthly_contribution=g["monthly_contribution"],
                target_date=g["target_date"],
                priority=g["priority"],
                status=g["status"],
            )
            for g in dataset.goals
            if g["customer_id"] == customer_id
        ],
        obligations=[
            ObligationRecord(
                id=str(o["id"]),
                obligation_type=o["obligation_type"],
                name=o["name"],
                amount=o["amount"],
                frequency=o["frequency"],
                next_due_date=o["next_due_date"],
                end_date=o["end_date"],
                is_essential=o["is_essential"],
                outstanding_principal=o["outstanding_principal"],
                interest_rate_apr=o["interest_rate_apr"],
                status=o["status"],
            )
            for o in dataset.obligations
            if o["customer_id"] == customer_id
        ],
        data_sharing_consent=profile["data_sharing_consent"],
    )
