-- =============================================================================
-- EXL Personalized Financial Advisor — initial relational schema
-- -----------------------------------------------------------------------------
-- * All money columns use NUMERIC(14,2) (exact decimal, never float).
-- * Every customer-owned table carries customer_id so ownership can be enforced
--   both in the API and by row-level security.
-- * Idempotent where practical (IF NOT EXISTS / CREATE OR REPLACE) so the file
--   can be re-applied to a development database safely.
-- * Works on Supabase and on plain PostgreSQL 15+ (a tiny `auth` shim is created
--   only when the Supabase `auth` schema does not exist).
-- =============================================================================

create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- Local-PostgreSQL compatibility shim (no-op on Supabase)
-- -----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'auth') then
    execute 'create schema auth';
    execute $f$
      create function auth.uid() returns uuid
      language sql stable
      as $body$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $body$
    $f$;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'create role anon nologin';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'create role authenticated nologin';
  end if;
  -- Least-privilege role used by the FastAPI backend. Login + password are
  -- granted manually per environment (see docs/security.md), never in Git.
  if not exists (select 1 from pg_roles where rolname = 'exl_api') then
    execute 'create role exl_api nologin';
  end if;
end
$$;

-- -----------------------------------------------------------------------------
-- Shared trigger: maintain updated_at
-- -----------------------------------------------------------------------------
create or replace function public.set_updated_at() returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

-- -----------------------------------------------------------------------------
-- 1. profiles — every person who can sign in, or a synthetic customer persona
-- -----------------------------------------------------------------------------
create table if not exists public.profiles (
  id                    uuid primary key default gen_random_uuid(),
  auth_user_id          uuid unique,                 -- Supabase auth.users.id (nullable for personas without login)
  role                  text not null check (role in ('customer', 'advisor')),
  display_name          text not null check (char_length(display_name) between 1 and 120),
  email                 text unique check (email is null or email = lower(email)),
  is_synthetic          boolean not null default true,
  data_sharing_consent  boolean not null default true,   -- consent to generate personalised insights
  marketing_consent     boolean not null default false,
  consent_updated_at    timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 2. customer_financial_profiles — 1:1 persona facts declared by the customer
-- -----------------------------------------------------------------------------
create table if not exists public.customer_financial_profiles (
  customer_id              uuid primary key references public.profiles (id) on delete cascade,
  persona_segment          text not null check (persona_segment in (
                             'young_salaried', 'family_goal_saver', 'pre_retiree', 'gig_worker',
                             'high_spender', 'debt_stressed', 'new_to_bank', 'stale_profile')),
  income_pattern           text not null check (income_pattern in ('salaried_stable', 'irregular', 'pension', 'unknown')),
  declared_monthly_income  numeric(14, 2) check (declared_monthly_income is null or declared_monthly_income >= 0),
  age_band                 text check (age_band is null or age_band in ('18-24', '25-34', '35-44', '45-54', '55-64', '65+')),
  dependents               smallint check (dependents is null or dependents between 0 and 10),
  city_tier                text check (city_tier is null or city_tier in ('tier_1', 'tier_2', 'tier_3')),
  risk_preference          text not null default 'unknown' check (risk_preference in ('conservative', 'balanced', 'growth', 'unknown')),
  currency                 char(3) not null default 'INR',
  profile_updated_at       timestamptz not null,       -- when the customer last confirmed these details
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 3. accounts — reported balances are *actual*; anything derived from
--    transactions is an *estimate* and is computed, never stored here.
-- -----------------------------------------------------------------------------
create table if not exists public.accounts (
  id                    uuid primary key default gen_random_uuid(),
  customer_id           uuid not null references public.profiles (id) on delete cascade,
  account_type          text not null check (account_type in ('savings', 'current', 'credit_card', 'fixed_deposit')),
  nickname              text not null check (char_length(nickname) between 1 and 60),
  masked_number         text not null check (masked_number ~ '^XXXX[0-9]{4}$'),
  currency              char(3) not null default 'INR',
  opening_balance       numeric(14, 2) not null,
  opening_balance_date  date not null,
  current_balance       numeric(14, 2),
  balance_as_of         timestamptz,
  is_liquid             boolean not null,             -- counts toward emergency-fund coverage
  status                text not null default 'active' check (status in ('active', 'closed')),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint accounts_id_customer_unique unique (id, customer_id),
  constraint accounts_customer_masked_unique unique (customer_id, masked_number),
  constraint accounts_balance_pair check ((current_balance is null) = (balance_as_of is null))
);
create index if not exists accounts_customer_idx on public.accounts (customer_id);

-- -----------------------------------------------------------------------------
-- 4. transactions — amount is always positive; direction gives the sign.
-- -----------------------------------------------------------------------------
create table if not exists public.transactions (
  id                       uuid primary key default gen_random_uuid(),
  account_id               uuid not null,
  customer_id              uuid not null,
  external_ref             text not null check (char_length(external_ref) between 1 and 64),
  posted_on                date not null,
  amount                   numeric(14, 2) not null check (amount > 0),
  direction                text not null check (direction in ('credit', 'debit')),
  transaction_type         text not null check (transaction_type in (
                             'salary', 'business_income', 'pension', 'interest', 'other_income',
                             'purchase', 'bill_payment', 'loan_payment', 'fee',
                             'transfer_in', 'transfer_out', 'refund', 'reversal')),
  category                 text not null check (category in (
                             'salary', 'business_income', 'pension', 'interest', 'other_income',
                             'rent', 'utilities', 'groceries', 'transport', 'insurance', 'healthcare',
                             'education', 'childcare', 'loan_emi',
                             'dining', 'shopping', 'entertainment', 'subscriptions', 'travel',
                             'personal_care', 'gifts', 'bank_fees', 'other_expense',
                             'transfer', 'uncategorized')),
  merchant_name            text check (merchant_name is null or char_length(merchant_name) <= 80),
  description              text not null check (char_length(description) between 1 and 200),
  transfer_group_id        uuid,
  reverses_transaction_id  uuid references public.transactions (id) on delete set null,
  created_at               timestamptz not null default now(),
  constraint transactions_account_owner_fk foreign key (account_id, customer_id)
    references public.accounts (id, customer_id) on delete cascade,
  constraint transactions_import_unique unique (account_id, external_ref),
  constraint transactions_direction_matches_type check (
    (direction = 'credit' and transaction_type in ('salary', 'business_income', 'pension', 'interest',
                                                   'other_income', 'transfer_in', 'refund', 'reversal'))
    or (direction = 'debit' and transaction_type in ('purchase', 'bill_payment', 'loan_payment', 'fee',
                                                     'transfer_out', 'reversal'))),
  constraint transactions_transfer_group check (
    (transaction_type in ('transfer_in', 'transfer_out')) = (transfer_group_id is not null)),
  constraint transactions_reversal_link check (
    (transaction_type = 'reversal') = (reverses_transaction_id is not null))
);
create index if not exists transactions_customer_posted_idx on public.transactions (customer_id, posted_on desc);
create index if not exists transactions_account_posted_idx on public.transactions (account_id, posted_on);
create index if not exists transactions_customer_category_idx on public.transactions (customer_id, category);
create index if not exists transactions_transfer_group_idx on public.transactions (transfer_group_id) where transfer_group_id is not null;

-- -----------------------------------------------------------------------------
-- 5. financial_goals
-- -----------------------------------------------------------------------------
create table if not exists public.financial_goals (
  id                    uuid primary key default gen_random_uuid(),
  customer_id           uuid not null references public.profiles (id) on delete cascade,
  name                  text not null check (char_length(name) between 1 and 80),
  goal_type             text not null check (goal_type in (
                          'emergency_fund', 'home_purchase', 'education', 'retirement', 'vehicle',
                          'travel', 'wedding', 'debt_payoff', 'other')),
  target_amount         numeric(14, 2) not null check (target_amount > 0),
  saved_amount          numeric(14, 2) not null default 0 check (saved_amount >= 0),
  monthly_contribution  numeric(14, 2) check (monthly_contribution is null or monthly_contribution >= 0),
  target_date           date,
  priority              smallint not null default 3 check (priority between 1 and 5),
  status                text not null default 'active' check (status in ('active', 'achieved', 'paused', 'cancelled')),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index if not exists financial_goals_customer_idx on public.financial_goals (customer_id, status);
create unique index if not exists financial_goals_customer_name_active_uidx
  on public.financial_goals (customer_id, lower(name)) where status <> 'cancelled';

-- -----------------------------------------------------------------------------
-- 6. financial_obligations — known commitments (EMIs, rent, premiums, fees)
-- -----------------------------------------------------------------------------
create table if not exists public.financial_obligations (
  id                     uuid primary key default gen_random_uuid(),
  customer_id            uuid not null references public.profiles (id) on delete cascade,
  obligation_type        text not null check (obligation_type in (
                           'loan_emi', 'rent', 'insurance_premium', 'credit_card_bill', 'school_fees',
                           'utility', 'subscription', 'tax', 'other')),
  name                   text not null check (char_length(name) between 1 and 80),
  amount                 numeric(14, 2) not null check (amount > 0),
  frequency              text not null check (frequency in ('monthly', 'quarterly', 'half_yearly', 'annual', 'one_time')),
  next_due_date          date not null,
  end_date               date,
  is_essential           boolean not null default true,
  outstanding_principal  numeric(14, 2) check (outstanding_principal is null or outstanding_principal >= 0),
  interest_rate_apr      numeric(5, 2) check (interest_rate_apr is null or interest_rate_apr between 0 and 60),
  status                 text not null default 'active' check (status in ('active', 'closed')),
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint financial_obligations_end_after_due check (end_date is null or end_date >= next_due_date)
);
create index if not exists financial_obligations_customer_due_idx
  on public.financial_obligations (customer_id, next_due_date) where status = 'active';

-- -----------------------------------------------------------------------------
-- 7. financial_products — generic, educational product *types* only.
--    No individual securities or specific investment products.
-- -----------------------------------------------------------------------------
create table if not exists public.financial_products (
  id                     uuid primary key default gen_random_uuid(),
  code                   text not null unique check (code ~ '^[A-Z0-9_]{3,40}$'),
  name                   text not null,
  product_type           text not null check (product_type in ('savings_feature', 'deposit', 'insurance', 'budgeting_tool', 'education')),
  description            text not null,
  is_investment_product  boolean not null default false check (is_investment_product = false),
  is_active              boolean not null default true,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 8. recommendation_rules — versioned rule catalogue (rules are immutable per version)
-- -----------------------------------------------------------------------------
create table if not exists public.recommendation_rules (
  rule_id      text not null check (rule_id ~ '^[A-Z0-9_]{3,60}$'),
  version      integer not null check (version >= 1),
  category     text not null check (category in (
                 'emergency_fund', 'goal_savings', 'discretionary_spending', 'upcoming_obligations',
                 'recurring_expenses', 'cash_flow_consistency', 'goal_celebration', 'missing_information')),
  name         text not null,
  description  text not null,
  parameters   jsonb not null default '{}'::jsonb,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  primary key (rule_id, version)
);

-- -----------------------------------------------------------------------------
-- 9. recommendations — persisted with the evidence used to produce them
-- -----------------------------------------------------------------------------
create table if not exists public.recommendations (
  id                   uuid primary key,             -- deterministic UUIDv5, see docs/recommendation-engine.md
  customer_id          uuid not null references public.profiles (id) on delete cascade,
  rule_id              text not null,
  rule_version         integer not null,
  category             text not null,
  subject_key          text not null check (char_length(subject_key) between 1 and 120),
  period_key           text not null check (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
  title                text not null check (char_length(title) between 1 and 160),
  explanation          text not null,
  reason               text not null,
  priority             text not null check (priority in ('high', 'medium', 'low')),
  priority_reason      text not null,
  evidence             jsonb not null,               -- inputs + calculations (traceability)
  assumptions          jsonb not null default '[]'::jsonb,
  suggested_actions    jsonb not null default '[]'::jsonb,
  confidence           text not null check (confidence in ('high', 'medium', 'low')),
  confidence_reason    text not null,
  data_as_of           date,                         -- latest transaction date used
  analytics_as_of      date not null,                -- evaluation date
  evidence_hash        text not null,
  status               text not null default 'pending' check (status in ('pending', 'accepted', 'dismissed', 'completed', 'expired')),
  status_changed_at    timestamptz,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint recommendations_rule_fk foreign key (rule_id, rule_version)
    references public.recommendation_rules (rule_id, version),
  constraint recommendations_dedup_unique unique (customer_id, rule_id, rule_version, subject_key, period_key)
);
create index if not exists recommendations_customer_status_idx on public.recommendations (customer_id, status, created_at desc);

-- -----------------------------------------------------------------------------
-- 10. recommendation_feedback
-- -----------------------------------------------------------------------------
create table if not exists public.recommendation_feedback (
  id                       uuid primary key default gen_random_uuid(),
  recommendation_id        uuid not null references public.recommendations (id) on delete cascade,
  customer_id              uuid not null references public.profiles (id) on delete cascade,
  submitted_by_profile_id  uuid not null references public.profiles (id),
  action                   text not null check (action in ('accepted', 'dismissed', 'completed', 'correction')),
  reason_code              text check (reason_code is null or reason_code in (
                             'not_relevant', 'already_doing_this', 'cannot_afford', 'income_incorrect',
                             'expense_incorrect', 'goal_outdated', 'transaction_miscategorized', 'other')),
  comment                  text check (comment is null or char_length(comment) <= 500),
  created_at               timestamptz not null default now(),
  constraint recommendation_feedback_correction_reason check (action <> 'correction' or reason_code is not null)
);
create index if not exists recommendation_feedback_rec_idx on public.recommendation_feedback (recommendation_id, created_at desc);
create index if not exists recommendation_feedback_customer_idx on public.recommendation_feedback (customer_id);

-- -----------------------------------------------------------------------------
-- 11. data_quality_events
-- -----------------------------------------------------------------------------
create table if not exists public.data_quality_events (
  id              uuid primary key default gen_random_uuid(),
  customer_id     uuid references public.profiles (id) on delete cascade,
  check_code      text not null check (char_length(check_code) between 1 and 60),
  severity        text not null check (severity in ('info', 'warning', 'error')),
  entity_type     text,
  entity_id       text,
  details         jsonb not null default '{}'::jsonb,
  detected_at     timestamptz not null default now(),
  resolved_at     timestamptz
);
create index if not exists data_quality_events_customer_idx on public.data_quality_events (customer_id, detected_at desc);

-- -----------------------------------------------------------------------------
-- 12. audit_events — append-only
-- -----------------------------------------------------------------------------
create table if not exists public.audit_events (
  id                uuid primary key default gen_random_uuid(),
  -- Plain IDs (no FKs): audit history must outlive the rows it describes and stay immutable.
  actor_profile_id  uuid,
  customer_id       uuid,
  action            text not null check (char_length(action) between 1 and 80),
  entity_type       text not null,
  entity_id         text,
  request_id        text,
  metadata          jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now()
);
create index if not exists audit_events_customer_idx on public.audit_events (customer_id, created_at desc);

create or replace function public.prevent_audit_mutation() returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_events is append-only';
end
$$;

-- -----------------------------------------------------------------------------
-- updated_at triggers (drop + create keeps this idempotent)
-- -----------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['profiles', 'customer_financial_profiles', 'accounts', 'financial_goals',
                           'financial_obligations', 'financial_products', 'recommendations']
  loop
    execute format('drop trigger if exists %I on public.%I', t || '_set_updated_at', t);
    execute format('create trigger %I before update on public.%I for each row execute function public.set_updated_at()',
                   t || '_set_updated_at', t);
  end loop;
end
$$;

drop trigger if exists audit_events_append_only on public.audit_events;
create trigger audit_events_append_only before update or delete on public.audit_events
  for each row execute function public.prevent_audit_mutation();
