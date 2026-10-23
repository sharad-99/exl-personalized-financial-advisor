# Product Requirements

**Product:** EXL Personalized Financial Advisor, presented to users as the "Financial Wellness Coach".
**Context:** academic EXL industry project. Indian retail banking, INR. **Synthetic data only.**
**Status:** working local demo. Not deployed (see `deployment.md`).

## 1. Problem statement

Retail bank customers can see their transactions but get little help understanding them. They want to know where
their money goes, whether they have a safety buffer, whether their goals are realistic, and what to do next.
Generic tips do not reflect a customer's own data. Opaque "AI" advice is hard to trust and hard for a bank to
justify to regulators. Banks need a way to give personalised, **explainable** and **safe** financial-wellness
guidance that shows the reasoning and numbers behind every suggestion, never pushes credit or investment products,
and handles incomplete data honestly.

## 2. Goals

1. Turn a customer's transactions, balances, obligations and goals into a clear picture of their finances.
2. Produce a small number of prioritised, actionable recommendations. Each one shows its inputs, calculations,
   assumptions and data confidence.
3. Help customers plan goals with monthly amounts that never exceed what their data supports.
4. Capture customer feedback (accept, dismiss, complete, "something's wrong") so the advice can be measured and
   improved.
5. Demonstrate engineering quality: exact money handling, determinism, test coverage, security and privacy by design.

Non-goals are listed in section 8.

## 3. Personas

| Persona (data segment) | Description | Primary needs |
|---|---|---|
| Young salaried earner (`young_salaried`) | 18–34, first or second job, card user | Build an emergency fund, control discretionary spend, first goals (trip, car) |
| Family saving for goals (`family_goal_saver`) | 35–54, dependents, school fees | Plan education and home goals, prepare for quarterly or annual payments, a larger emergency buffer (6 months with 2+ dependents) |
| Near-retirement (`pre_retiree`) | 55–64, salaried or pension | Protect liquidity, top up retirement and medical reserves, low-risk guidance |
| Gig / freelance worker (`gig_worker`) | Irregular income | Smooth cash flow, a larger buffer (6 months), set aside part of large payouts |
| High spender (`high_spender`) | Strong income, high discretionary and subscription spend | Visibility into spending spikes and recurring charges |
| Debt-stressed (`debt_stressed`) | High EMI and essential share, thin buffer | Cash-flow consistency and an emergency buffer without being offered more credit |
| New-to-bank (`new_to_bank`) | Little history | Honest "we need more data" messaging instead of guesses |
| Advisor / EXL analyst (demo role) | Internal user | Read-only view of all synthetic customers to review insights |

A `stale_profile` segment exists only to exercise stale or missing-data handling.

## 4. User stories by screen

### Login (`/login`)
- As a customer, I sign in with email and password. Invalid credentials show one generic error that does not
  reveal whether the account exists.
- As a visitor who opens a protected page, I am sent to login and returned to that page afterwards (internal
  paths only).
- In local demo mode, the login page explains the synthetic demo accounts.

### Dashboard (`/dashboard`)
- As a customer, I see income, expenses, net observed cash flow and savings rate, averaged over the complete
  months that have data, with the period stated.
- I see income vs expenses by month, where my money went by category, emergency-fund coverage, goal progress and
  my top recommendations.
- When a figure cannot be calculated, I see "not available" and the reason, never a misleading zero.

### Profile (`/customers`, `/customers/{id}`; "Customers" for advisors)
- As a customer, I see my financial profile, accounts (masked numbers, reported balances and their dates),
  obligations and transaction summary.
- As an advisor, I can search and filter synthetic customers by segment and open any profile read-only.

### Money coach (`/insights`)
- As a customer, I see personalised recommendations ordered by priority. Each shows a title, explanation, reason,
  suggested actions, assumptions, confidence, and the evidence (inputs and calculations).
- I can accept, dismiss (with a reason), mark completed, or report that something is wrong (a correction with a
  reason code such as "income incorrect").
- I can re-check my insights against current data and see what was created, updated or no longer applies, and
  which rules were paused and why.

### Goals (`/goals`)
- As a customer, I can create and edit goals (name, type, target, saved amount, monthly contribution, target date,
  priority) and see progress. The API also accepts status changes (`active`, `achieved`, `paused`, `cancelled`),
  but the current goal form does not expose them.
- For each goal, I see whether it is on track and the monthly amount required. If it is behind, I see a safe
  suggestion: an increase that fits my estimated capacity, or a later target date.
- Validation prevents impossible input: a target date in the past, saved amount greater than target, duplicate
  names, more than 20 goals.

### History (`/recommendations`)
- As a customer, I can filter past recommendations by status (pending, accepted, dismissed, completed, expired)
  and see the evidence as it was when the advice was given, plus my feedback history.

### Settings (`/settings`)
- As a customer, I see data freshness (latest transaction, history length, balance status, confidence).
- I can withdraw or give consent for personalised insights and for marketing. Withdrawing insight consent stops
  new recommendations, and re-checking clears open ones.

## 5. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Authenticate users (Supabase Auth in deployments, dev-only local login in development) and resolve each user to a linked profile |
| FR-2 | Customers access only their own data. Advisors read all synthetic customers and cannot write |
| FR-3 | Classify transactions as income, expense, refund or excluded (internal transfer, duplicate, reversal), with the reason, and show the classification per transaction |
| FR-4 | Compute analytics on request: totals, averages over months with data, savings rate, categories, trend, month-over-month, recurring expenses, income stability, balances and reconciliation, emergency fund, savings capacity, 30-day obligations, goal plans, data quality and confidence |
| FR-5 | Generate recommendations from 8 versioned rules with priority, a priority reason, evidence, assumptions, actions and confidence. Suppress rules when data is missing, confidence is low, or consent is withdrawn, and record why |
| FR-6 | Persist recommendations with stable IDs. Do not duplicate them on refresh. Never overwrite customer decisions. Expire pending items that no longer apply. Do not re-raise accepted subjects, or subjects dismissed within the last 60 days |
| FR-7 | Record feedback with an enforced status workflow. Corrections require a reason code |
| FR-8 | Create and update goals with validation, and plan them against one shared, conservative capacity pool (50% of capacity, emergency fund first) |
| FR-9 | Manage consent, with timestamps |
| FR-10 | Audit security-relevant actions in an append-only log without free text or tokens |
| FR-11 | Generate, validate and seed reproducible synthetic data (60 customers, 8 personas, 13+ months, edge cases) |
| FR-12 | Provide documented OpenAPI and a consistent error envelope |

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Explainability | Every recommendation is traceable to rule id and version, inputs, calculations and thresholds. Customer text is built only from computed facts |
| Determinism | Same data, evaluation date and rule versions give identical analytics and recommendations |
| Accuracy | Exact decimal money (`NUMERIC(14,2)`, `Decimal`, integer paise). No floats. Money is sent as strings in JSON |
| Data honesty | Missing data is never treated as zero. Confidence is shown. Low confidence pauses dependent advice |
| Safety | No loan or credit offers, no securities or specific investment products, no transaction execution |
| Security | Server-held tokens in httpOnly cookies, CSRF checks, strict CORS, RLS, least-privilege database role, rate limiting, size and time limits, log redaction (see `security.md`) |
| Privacy | Synthetic data only. Masked account numbers. Reserved `.test` emails. Consent controls. Data minimisation in logs and audit |
| Performance | Interactive responses for one customer's data (about 400 transactions per customer). 15 s hard request timeout and 10 s database statement timeout |
| Accessibility | Keyboard-reachable navigation, a skip link, labelled controls |
| Maintainability | Layered backend (routes, deps, services, repositories). Typed code. ruff, ESLint and TypeScript checks. 228 backend tests and 4 e2e tests |
| Portability | Runs locally with SQLite and no external services. Deploys on Supabase, any Python host and Vercel |

## 7. KPIs

These are the KPIs from the team's plan. The demo stores the data needed to compute the starred ones, but no
analytics dashboard or event tracking is built.

| KPI | Definition | Data source in this system |
|---|---|---|
| Engagement | Share of active customers who open the money coach or goals each month; recommendations viewed per customer | Not instrumented. Would need page-view or event tracking |
| Recommendation acceptance rate (*) | accepted ÷ (accepted + dismissed) per rule and overall, over a period | `recommendation_feedback.action`, `recommendations.status` |
| Correction rate (*) | corrections ÷ recommendations shown. A high rate signals data or rule problems | `recommendation_feedback` (`action = 'correction'`, `reason_code`) |
| Savings-rate change | Change in a customer's savings rate over time after engaging with advice | Computable from transactions with `compute_analytics` over successive periods. Meaningful only with real longitudinal data |
| Goal progress (*) | Share of goals on track, or achieved by their target date | `financial_goals` plus goal plans |
| Retention | Customers returning month over month | Not instrumented. Would need sign-in or session events (local logins are audited as `auth.local_login`) |

## 8. Out of scope

- **Real bank integration.** No core-banking, account-aggregator or payment rails, and no real customer data.
- **Investment product advice.** No securities, mutual funds, crypto or specific products. In India, investment
  advice is regulated by SEBI (Investment Advisers Regulations), and banks' customer-data handling and digital
  lending are governed by RBI directions. A real launch would need regulatory and legal review, including data
  protection under the Digital Personal Data Protection Act, 2023. This demo does not claim compliance.
- **Credit and loan recommendations,** or any transaction execution.
- **LLMs or ML models** for generating advice. All advice is rule-based and deterministic.
- Mobile apps, notifications, multi-language support, MFA, and production operations (monitoring, on-call, SLAs).

## 9. Success criteria for the academic demo

1. End-to-end journey works locally: sign in as a synthetic customer, view the dashboard and money coach, give
   feedback, create or edit a goal, change consent, sign out. The advisor view is read-only. This is covered by
   the Playwright tests (4 passing).
2. Every recommendation for all 60 synthetic customers is traceable and passes the safety checks (automated test
   over every customer).
3. Calculations are verified by unit tests with hand-computed expectations, and money is exact.
4. Missing or stale data produces explicit "unknown" states and data requests, never fabricated numbers.
5. Security controls are demonstrated by tests: authentication on every route, cross-customer isolation, advisor
   read-only, no secrets in responses, RLS on PostgreSQL.
6. Synthetic data is reproducible from a seed and validates with zero errors.
7. Documentation (this `docs/` folder) matches the code, and deployment is prepared but explicitly marked as not
   yet executed.
