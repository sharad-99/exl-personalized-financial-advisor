# Synthetic Data

> **All data in this project is fabricated.** Names, employers, merchants, references, balances and amounts are
> invented by `backend/app/synthetic_data/generator.py`. Masked account numbers are random 4-digit suffixes, not
> real account numbers. This data must **never** be presented as real bank or customer data. Every profile is
> flagged `is_synthetic = true`, and the API and UI label responses as synthetic.

## 1. What is generated

| Item | Value (default) |
|---|---|
| Customers | **60**, plus 1 advisor profile (`advisor@demo.exl.test`, "EXL Demo Analyst") |
| History | **13 complete calendar months plus the current partial month**, up to `as_of` (`history_months=13`, minimum 12) |
| Currency / context | INR, Indian names, cities by tier, UPI / NEFT / IMPS / BBPS-style descriptions |
| Generator version | `1.0.0` |

With `--seed 42 --as-of 2026-10-24` the generator produces 119 accounts, 22,926 transactions, 87 goals and
146 obligations. These figures come from the validator's statistics for that seed and date.

### Personas (`PERSONAS`)

| Segment | Count | Income pattern | Monthly income (Rs) | Notable traits |
|---|---|---|---|---|
| `young_salaried` | 10 | salaried_stable | 35,000–90,000 | Ages 18–34. Card 70% of the time, recurring deposit 60% |
| `family_goal_saver` | 10 | salaried_stable | 80,000–2,20,000 | 1–3 dependents. Recurring deposit 90%, school fees |
| `pre_retiree` | 7 | salaried_stable (30% become `pension`) | 90,000–2,50,000 | Age 55–64. High liquid buffer, no rent |
| `gig_worker` | 7 | irregular | 25,000–80,000 | 2–6 variable payouts a month. Monthly total is 0.35×–1.8× the base |
| `high_spender` | 7 | salaried_stable | 70,000–1,80,000 | Discretionary 48–62% of income, 4–6 subscriptions, spikes in festive and recent months, always has a card |
| `debt_stressed` | 7 | salaried_stable | 40,000–1,10,000 | Always has a loan EMI (15–32% of income). Essentials 66–80% of income, low buffer |
| `new_to_bank` | 5 | salaried_stable | 30,000–70,000 | **Short history:** one complete month plus the current partial month |
| `stale_profile` | 7 | unknown | 30,000–1,20,000 | Data ends 50–130 days before `as_of`. Profile not confirmed for more than a year. Missing income or balance on some customers |

Personas are assigned in the table order, so customers 1–10 are `young_salaried`, 11–20 are `family_goal_saver`,
and so on. If `--customers` exceeds 60, the personas repeat in the same order.

## 2. Determinism

- **Inputs:** `generate_dataset(seed=42, as_of=..., history_months=13, customer_count=None)`. Identical
  `(seed, as_of, customer_count, history_months)` produce byte-identical output. **Pass `--as-of`** to get
  reproducible output, because it defaults to today's date in UTC.
- **Randomness:** each customer has its own RNG, `random.Random(f"{seed}:customer:{index}")`. Changing one
  customer does not shift any other customer.
- **IDs:** every ID is a **UUIDv5**:
  - customers: `uuid5(ID_NAMESPACE, f"{seed}:{index}:<kind>:...")`
  - advisor: `uuid5(ID_NAMESPACE, f"{seed}:advisor:...")`

  This applies to profiles, `auth_user_id`, accounts, transactions, goals, obligations and transfer groups.
- **Money:** amounts are generated as **integer paise** and converted to `Decimal` with `from_paise`. Floats are
  used only for ratios and probabilities, never as stored amounts.
- `tests/unit/test_synthetic_data.py::test_dataset_is_reproducible_and_seed_sensitive` checks both properties:
  the same inputs reproduce the output, and a different seed changes it.
- `tests/unit/test_synthetic_data_quality.py::test_exact_record_counts_and_fingerprint` pins the exact output for
  seed 42 / as_of 2026-10-24: 61 profiles, 60 financial profiles, 119 accounts, 22,872 transactions, 85 goals,
  146 obligations, and a SHA-256 fingerprint of all rows. An intentional generator change must update these
  golden values (and this document); an unintentional one fails CI.

## 3. Transaction patterns (per customer, per month)

| Pattern | Details |
|---|---|
| Salary / pension | Credited on day 1 to the savings account: `NEFT/SALARY/<EMPLOYER>`. An 8% increase applies from April of the `as_of` year. Pension customers get type `pension` |
| Gig income | 2–6 `business_income` credits on random days from fictional platforms (for example "FreelanceHub Payout") |
| Interest | Quarterly (Mar, Jun, Sep, Dec, on the 28th), Rs 80–900 |
| Rent | 65% of non-pre-retiree customers, 18–28% of income, paid on days 3–5 (`IMPS/RENT/LANDLORD PAYMENT`) |
| Loan EMI | Day 5 (`ACH/EMI/HOMESTEAD FINANCE LOAN`), with probability set by the persona |
| Utilities | Electricity Rs 900–3,200 (days 8–12) and broadband Rs 999 (day 10) |
| School fees | Quarterly (Jan, Apr, Jul, Oct) for `family_goal_saver` and `debt_stressed` customers with dependents |
| Insurance | Annual premium for 60% of customers. Last year's payment falls inside the history, and the next one is an obligation due 3–25 or 40–300 days after `as_of` |
| Variable essentials | Groceries (5 UPI purchases), transport (6) and healthcare (1), split from the essential budget |
| Subscriptions | Fixed amount on day 14 (StreamFlix, TuneBox, CloudVault, ...), charged to the card when one exists. These are detected as recurring |
| Discretionary | Dining, shopping, entertainment, travel, personal care and gifts as POS purchases. Dining, shopping and travel go on the card if one exists. `high_spender` months in October, November and the last two months are 1.3–1.6× higher |
| Bank fees | About 5% of months, Rs 2–6 SMS alert charges |
| **Card bill payment** | On the 18th, the previous month's card spend minus card refunds is paid as an **internal transfer**: `transfer_out` from savings and `transfer_in` to the card, sharing one `transfer_group_id`. Analytics exclude both legs, so card spend is counted once (as purchases) and never again as a bill |
| **Auto-sweep to recurring deposit** | Customers with a deposit account sweep on the 27th. The amount is the month's net savings inflow minus a retained buffer (2–12% of income), rounded down to whole Rs 100, and the sweep happens only if it is at least Rs 1,000. It is an internal transfer from savings to the `fixed_deposit` account nicknamed "Recurring Deposit", which analytics report as `observed_monthly_transfers_to_savings` |

### Accounts
- Every customer has a liquid savings account ("Primary Savings"). Some also have a credit card (opening balance
  0, where a negative balance means an amount owed) or a fixed deposit (opening balance Rs 20,000–4,00,000).
- The savings opening balance is chosen so that the ending balance is about `liquid_months` × essential spend,
  and so that the running balance never drops below Rs 500.
- `current_balance` = opening + signed non-duplicate transactions. `balance_as_of` is 23:00 UTC on the customer's
  last data date.

### Goals and obligations
- **Goals** come from persona templates, for example "Emergency Fund", "Child Education Fund", "Home Down
  Payment" and "Retirement Corpus Top-up". The target is income × a multiple. Progress is chosen from 10% to 100%.
  The target date is 4–48 months after `as_of`. 25% of goals have no planned contribution. A goal is `achieved`
  when saved >= target.
- **Obligations:** monthly rent, loan EMI (with outstanding principal and an APR of 9.25–16.50%), annual insurance
  premium, quarterly school fees, a monthly credit-card bill, and a one-time "Advance Tax Instalment" for
  customers where `index % 7 == 3`.

## 4. Deliberate edge cases

| Edge case | Who | Effect | Count (seed 42) |
|---|---|---|---|
| Refund | `index % 4 == 0` | Credit `refund` of a random savings-account purchase, 5 days later | 15 |
| Reversal | `index % 5 == 0` | Same-day credit `reversal` linked by `reverses_transaction_id`. Both legs are neutralised | 12 |
| Duplicate import | `index % 6 == 0` | Two purchases copied with external_ref `<ref>-DUP` and a new ID, but the same account, date, amount and description. Excluded as `probable_duplicate` | 20 rows |
| Uncategorised | any customer, about 4% of grocery, transport and healthcare purchases | Stored as `uncategorized`. Keyword rules recover all of them for seed 42 | 345 rows |
| Stale data | all `stale_profile` customers | Last transaction 50–130 days before `as_of`, balance as of that date, profile older than 365 days, so confidence is **low** | 7 customers |
| Missing income | `stale_profile` and `index % 2 == 0` | `declared_monthly_income = null` **and** no income credits (salary is paid into another bank). Analytics report income as unknown (`null`), never zero, and raise `missing_income` | 4 |
| Missing balance | `stale_profile` and `index % 3 == 0` | Savings `current_balance` and `balance_as_of` are null, so the emergency fund is `unknown` | 3 accounts |
| Short history | all `new_to_bank` customers | Fewer than 3 complete months, so confidence is **low** | 5 customers |

The missing-income customers have neither declared income nor any income credits, so the `missing_income`
data-quality issue fires for all 4, their monthly-average income and net cash flow are `null` (unknown), and the
savings rate status is `no_income`.

## 5. Privacy-safe identifiers

- **Emails:** `customerNN@demo.exl.test` (`NN` = 01–60) and `advisor@demo.exl.test`. `.test` is a reserved
  top-level domain that can never receive mail.
- **Masked numbers:** account numbers are `XXXX` followed by 4 random digits. The database enforces
  `^XXXX[0-9]{4}$`. The validator rejects any description containing 9 or more consecutive digits.
- **Names:** generated from common Indian first and last names. Employers, merchants and platforms are fictional.
- `test_no_real_looking_identifiers` asserts these properties.

## 6. Validation (`backend/app/synthetic_data/validation.py`)

`validate_dataset(ds, min_customers=50, min_history_months=12)` returns a report with `errors`, `warnings` and
`stats`. `ok` is true when there are no errors.

**Errors** (invalid records that would break the schema or analytics):
- Fewer than 50 customers. A profile not flagged synthetic. An email outside `demo.exl.test`. Duplicate emails.
  A customer without a financial profile.
- An account referencing an unknown customer, with a bad mask format, a duplicate mask for the same customer, or
  a balance without `balance_as_of` (or the reverse).
- A transaction on an unknown account, or on an account owned by a different customer. Amount <= 0 or not at
  2 decimal places. Type does not match direction. Dated after `as_of` or before the account's opening date. A
  digit run of 9 or more in the description.
- A transfer without a group. A transfer group that does not have exactly 2 legs summing to 0. A reversal that
  does not match its original (different customer or amount). Duplicate `(account_id, external_ref)` pairs.
- An account balance that does not reconcile (opening + signed non-duplicate transactions ≠ current). A liquid
  account with a negative balance.
- A customer with no transactions, or with a history span under 11 months (except `new_to_bank` and `stale_profile`).
- **Classification consistency** (runs the production classifier, `spending_categorization.classify_transactions`,
  over every customer): a category that contradicts its transaction type (e.g. a purchase categorised as salary,
  a transfer not categorised `transfer`); the duplicate detector not finding exactly the injected duplicates
  (misses or false positives); any unmatched transfer leg or orphan reversal; more than 2% of expenses still
  uncategorised after keyword rules.
- A goal or obligation with an unknown customer or an invalid amount. Saved > target on a goal that is not
  achieved. An obligation whose end date is before its due date.

**Warnings** (deliberate edge cases):
- Duplicate imports present
- Reversals without an original
- New-to-bank customers with short histories
- Customers without declared income
- Accounts without a reported balance

For seed 42 and as_of 2026-10-24 there are 0 errors and 4 warnings: 20 duplicate imports, 5 short histories,
4 without declared income, and 3 without a balance. `stats` also reports the classifier outcome: 1,249 income,
20,118 expense, 15 refund and 1,490 excluded transactions; 1,446 internal-transfer legs, 20 duplicates detected
(= 20 injected), 12 reversal pairs, 0 uncategorised after rules.

## 7. Commands

Load the data into a database (SQLite by default; the schema is created from the ORM):
```bash
cd backend
.venv/bin/python -m app.synthetic_data.seed --seed 42 --reset
# options: --as-of YYYY-MM-DD  --customers N (>=50)  --history-months N (>=12)  --allow-production
```
- Without `--reset`, the seeder refuses to run if synthetic rows already exist (exit code 1).
- `--reset` deletes only rows that belong to `is_synthetic = true` profiles.
- With `ENVIRONMENT=production`, the seeder refuses to run (exit code 2) unless `--allow-production` is given.
- The seeder also loads reference data (rules and products) and writes `data_quality_events` for each customer.
- For PostgreSQL, apply the migrations first (`python -m app.db.migrate`).

Export to files (run from the repository root):
```bash
backend/.venv/bin/python scripts/generate_synthetic_data.py --seed 42 --as-of 2026-10-24 --out data/generated
```
This writes `profiles`, `financial_profiles`, `accounts`, `transactions`, `goals` and `obligations` as both
`.csv` and `.json`, plus a `manifest.json` containing the seed, as_of, generator version, counts and a synthetic
data notice. `data/generated/` is git-ignored.

Validate:
```bash
backend/.venv/bin/python scripts/validate_synthetic_data.py --seed 42 [--as-of YYYY-MM-DD] [--customers N]
```
The script prints the statistics, every warning and error, and `RESULT: PASS` or `FAIL`. It **exits non-zero
when there are errors**. CI runs it on every push. `make data` and `make validate` wrap both scripts.

Load into Supabase (owner connection string in the git-ignored `backend/.env.supabase`):
```bash
cd backend
set -a; . ./.env.supabase; set +a
.venv/bin/python -m app.db.migrate
.venv/bin/python -m app.synthetic_data.seed --seed 42 --as-of 2026-10-24 --reset
.venv/bin/python ../scripts/link_supabase_users.py --apply   # after creating demo users in Supabase Auth
```
`link_supabase_users.py` sets `profiles.auth_user_id` for synthetic profiles whose email matches a Supabase Auth
user (dry run without `--apply`). `--reset` keeps existing links.

## 8. Tests

| File | What it checks |
|---|---|
| `tests/unit/test_synthetic_data.py` | volume, reproducibility, seed sensitivity, persona coverage, 12+ months, identifiers, validator catches injected errors, reference SQL matches code, `--reset` keeps auth links |
| `tests/unit/test_synthetic_data_quality.py` | golden counts + fingerprint, other as_of dates and larger customer counts stay valid, classifier statistics, scenario coverage (recurring bills, debt, irregular income, income-elsewhere, goal states, all four emergency-fund states), validator flags 5 kinds of injected inconsistency, seeding loads every record, SQLite constraints (duplicate import, non-positive amount, bad direction, unknown account, wrong owner) |
| `tests/integration/test_postgres.py` | on real PostgreSQL: migrations re-run cleanly, CHECK/FK/UNIQUE constraints (direction vs type, transfer group, category, overflow, duplicate import, masked number, negative saved amount, no investment products), append-only audit, RLS isolation, exact NUMERIC(14,2) |

