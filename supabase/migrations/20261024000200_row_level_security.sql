-- =============================================================================
-- Row-level security and least-privilege grants
-- -----------------------------------------------------------------------------
-- Defence in depth: the FastAPI backend already authorises every request, but
-- RLS guarantees that a Supabase client using the public anon key (or a stolen
-- customer token) can never read another customer's rows directly through
-- PostgREST. Customers get read-only access to their own rows; all writes go
-- through the backend (role exl_api). The anon role gets nothing.
-- =============================================================================

-- Helper functions. SECURITY DEFINER so policies can resolve the caller's
-- profile without recursive RLS evaluation on profiles.
create or replace function public.current_profile_id() returns uuid
language sql stable security definer set search_path = public
as $$
  select id from public.profiles where auth_user_id = auth.uid()
$$;

create or replace function public.current_user_is_advisor() returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (select 1 from public.profiles where auth_user_id = auth.uid() and role = 'advisor')
$$;

revoke all on function public.current_profile_id() from public;
revoke all on function public.current_user_is_advisor() from public;
grant execute on function public.current_profile_id() to authenticated, exl_api;
grant execute on function public.current_user_is_advisor() to authenticated, exl_api;

-- Enable RLS everywhere --------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['profiles', 'customer_financial_profiles', 'accounts', 'transactions',
                           'financial_goals', 'financial_obligations', 'financial_products',
                           'recommendation_rules', 'recommendations', 'recommendation_feedback',
                           'data_quality_events', 'audit_events']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('revoke all on public.%I from authenticated', t);
  end loop;
end
$$;

-- Grants -----------------------------------------------------------------------
grant usage on schema public to authenticated, exl_api;

grant select on public.profiles, public.customer_financial_profiles, public.accounts,
  public.transactions, public.financial_goals, public.financial_obligations,
  public.financial_products, public.recommendation_rules, public.recommendations,
  public.recommendation_feedback to authenticated;

grant select, insert, update on public.profiles, public.customer_financial_profiles,
  public.accounts, public.transactions, public.financial_goals, public.financial_obligations,
  public.financial_products, public.recommendation_rules, public.recommendations,
  public.data_quality_events to exl_api;
grant select, insert on public.recommendation_feedback, public.audit_events to exl_api;

-- Policies (drop-if-exists keeps the migration re-runnable) ---------------------
do $$
declare
  t text;
begin
  -- Customer-owned tables: owner or advisor may read.
  foreach t in array array['customer_financial_profiles', 'accounts', 'transactions', 'financial_goals',
                           'financial_obligations', 'recommendations', 'recommendation_feedback']
  loop
    execute format('drop policy if exists %I on public.%I', t || '_owner_or_advisor_read', t);
    execute format(
      'create policy %I on public.%I for select to authenticated
         using (customer_id = public.current_profile_id() or public.current_user_is_advisor())',
      t || '_owner_or_advisor_read', t);
  end loop;

  -- Backend service role: full DML within granted privileges.
  foreach t in array array['profiles', 'customer_financial_profiles', 'accounts', 'transactions',
                           'financial_goals', 'financial_obligations', 'financial_products',
                           'recommendation_rules', 'recommendations', 'recommendation_feedback',
                           'data_quality_events', 'audit_events']
  loop
    execute format('drop policy if exists %I on public.%I', t || '_backend_all', t);
    execute format('create policy %I on public.%I for all to exl_api using (true) with check (true)',
                   t || '_backend_all', t);
  end loop;
end
$$;

drop policy if exists profiles_self_or_advisor_read on public.profiles;
create policy profiles_self_or_advisor_read on public.profiles for select to authenticated
  using (auth_user_id = auth.uid() or public.current_user_is_advisor());

drop policy if exists financial_products_read on public.financial_products;
create policy financial_products_read on public.financial_products for select to authenticated
  using (is_active);

drop policy if exists recommendation_rules_read on public.recommendation_rules;
create policy recommendation_rules_read on public.recommendation_rules for select to authenticated
  using (true);
