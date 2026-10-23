// Types mirroring the FastAPI response models (backend/app/schemas).
// Money values arrive as exact decimal strings, e.g. "12345.67".

export type Money = string;
export type ISODate = string;
export type Confidence = "high" | "medium" | "low";
export type Priority = "high" | "medium" | "low";
export type RecommendationStatus = "pending" | "accepted" | "dismissed" | "completed" | "expired";

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string; details?: { loc: string[]; msg: string }[] };
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}

export interface Me {
  profile_id: string;
  role: "customer" | "advisor";
  display_name: string;
  email: string | null;
  customer_id: string | null;
  is_synthetic: boolean;
  data_sharing_consent: boolean;
  marketing_consent: boolean;
  consent_updated_at: string | null;
}

export interface CustomerSummary {
  id: string;
  display_name: string;
  persona_segment: string | null;
  income_pattern: string | null;
  is_synthetic: boolean;
}

export interface Account {
  id: string;
  account_type: string;
  nickname: string;
  masked_number: string;
  currency: string;
  current_balance: Money | null;
  balance_as_of: string | null;
  is_liquid: boolean;
  status: string;
}

export interface Obligation {
  id: string;
  obligation_type: string;
  name: string;
  amount: Money;
  frequency: string;
  next_due_date: ISODate;
  end_date: ISODate | null;
  is_essential: boolean;
  outstanding_principal: Money | null;
  interest_rate_apr: string | null;
  status: string;
}

export interface Goal {
  id: string;
  name: string;
  goal_type: string;
  target_amount: Money;
  saved_amount: Money;
  monthly_contribution: Money | null;
  target_date: ISODate | null;
  priority: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerDetail {
  id: string;
  display_name: string;
  is_synthetic: boolean;
  data_sharing_consent: boolean;
  financial_profile: {
    persona_segment: string;
    income_pattern: string;
    declared_monthly_income: Money | null;
    age_band: string | null;
    dependents: number | null;
    city_tier: string | null;
    risk_preference: string;
    currency: string;
    profile_updated_at: string;
  } | null;
  accounts: Account[];
  obligations: Obligation[];
  goals: Goal[];
  transaction_summary: {
    transaction_count: number;
    first_transaction_date: ISODate | null;
    last_transaction_date: ISODate | null;
  };
}

export interface Transaction {
  id: string;
  account_id: string;
  posted_on: ISODate;
  amount: Money;
  direction: "credit" | "debit";
  transaction_type: string;
  category: string;
  effective_category: string;
  category_source: string;
  merchant_name: string | null;
  description: string;
  counted_as: "income" | "expense" | "refund" | "excluded";
  exclusion_reason: string | null;
}

export interface GoalPlan {
  goal_id: string;
  name: string;
  progress_pct: string;
  remaining_amount: Money;
  months_remaining: number | null;
  required_monthly: Money | null;
  planned_monthly: Money | null;
  plan_status: "achieved" | "on_track" | "behind" | "no_target_date" | "overdue" | "inactive";
  projected_completion: ISODate | null;
  suggested_increase: Money | null;
  suggested_target_date: ISODate | null;
  guidance: string;
  calculation: Record<string, string>;
  assumptions: string[];
}

export interface GoalWithPlan {
  goal: Goal;
  plan: GoalPlan | null;
}

export interface QualityIssue {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  count: number;
}

export interface Analytics {
  customer_id: string;
  currency: string;
  is_synthetic_data: boolean;
  period: { start_date: ISODate; end_date: ISODate; as_of: ISODate; months_in_period: number; months_with_data: number };
  totals: {
    total_income: Money;
    total_expenses: Money;
    refunds_netted: Money;
    net_observed_cash_flow: Money;
    excluded_internal_transfers: Money;
    excluded_duplicates: Money;
    excluded_reversal_pairs: number;
    note: string;
  };
  monthly_averages: {
    income: Money | null;
    expenses: Money | null;
    essential_expenses: Money | null;
    discretionary_expenses: Money | null;
    net_observed_cash_flow: Money | null;
    basis_months: number;
  };
  savings_rate: { value_pct: string | null; status: string; formula: string; reason: string | null };
  spending_by_category: { category: string; group: string; amount: Money; share_pct: string | null; transaction_count: number }[];
  monthly_trend: {
    month: string;
    income: Money;
    expenses: Money;
    essential_expenses: Money;
    discretionary_expenses: Money;
    net_observed_cash_flow: Money;
    has_data: boolean;
    is_partial: boolean;
  }[];
  month_over_month: { month: string; expenses: Money; previous_expenses: Money | null; change_amount: Money | null; change_pct: string | null }[];
  recurring_expenses: {
    merchant: string;
    category: string;
    average_amount: Money;
    occurrences: number;
    months_observed: number;
    last_date: ISODate;
    next_expected_date: ISODate;
    is_subscription: boolean;
  }[];
  income_stability: { months_with_income: number; coefficient_of_variation: string | null; pattern: string; declared_monthly_income: Money | null };
  balances: {
    reported_liquid_balance: Money | null;
    liquid_balance_status: "fresh" | "stale" | "missing";
    credit_card_outstanding: Money | null;
    accounts: {
      account_id: string;
      nickname: string;
      account_type: string;
      masked_number: string;
      is_liquid: boolean;
      reported_balance: Money | null;
      balance_as_of: string | null;
      balance_is_stale: boolean | null;
      estimated_balance_from_transactions: Money;
      reconciliation_difference: Money | null;
    }[];
    note: string;
  };
  emergency_fund: {
    liquid_balance: Money | null;
    average_monthly_essential_expenses: Money | null;
    coverage_months: string | null;
    target_months: number;
    target_amount: Money | null;
    gap_amount: Money | null;
    status: "sufficient" | "building" | "insufficient" | "unknown";
    reason: string | null;
    assumptions: string[];
  };
  savings_capacity: {
    average_monthly_net_cash_flow: Money | null;
    recent_3_month_net_cash_flow: Money | null;
    non_monthly_obligation_provision: Money;
    estimated_monthly_capacity: Money | null;
    observed_monthly_transfers_to_savings: Money | null;
    reason: string | null;
    calculation: Record<string, string>;
  };
  upcoming_obligations: {
    horizon_days: number;
    total_due: Money;
    items: { obligation_id: string; name: string; obligation_type: string; amount: Money; frequency: string; due_date: ISODate; days_until_due: number; is_essential: boolean }[];
  };
  goals: (GoalPlan & { target_amount: Money; saved_amount: Money; target_date: ISODate | null; priority: number })[];
  data_quality: {
    latest_transaction_date: ISODate | null;
    days_since_last_transaction: number | null;
    freshness: "fresh" | "aging" | "stale" | "no_data";
    history_months: number;
    profile_age_days: number | null;
    balance_status: "fresh" | "stale" | "missing";
    issues: QualityIssue[];
    confidence: Confidence;
    confidence_reasons: string[];
  };
}

export interface Recommendation {
  id: string;
  customer_id: string;
  rule_id: string;
  rule_version: number;
  category: string;
  title: string;
  explanation: string;
  reason: string;
  priority: Priority;
  priority_reason: string;
  evidence: { inputs?: Record<string, unknown>; calculations?: Record<string, unknown>; thresholds?: Record<string, unknown> };
  assumptions: string[];
  suggested_actions: string[];
  confidence: Confidence;
  confidence_reason: string;
  data_as_of: ISODate | null;
  analytics_as_of: ISODate;
  period_key: string;
  status: RecommendationStatus;
  status_changed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecommendationList extends Paginated<Recommendation> {
  is_synthetic_data: boolean;
}

export interface RefreshResult {
  created: number;
  updated: number;
  unchanged: number;
  expired: number;
  as_of: ISODate;
  confidence: Confidence;
  confidence_reason: string;
  suppressed_rules: { rule_id: string; reason: string }[];
  active: Recommendation[];
}

export type FeedbackAction = "accepted" | "dismissed" | "completed" | "correction";
export type FeedbackReason =
  | "not_relevant"
  | "already_doing_this"
  | "cannot_afford"
  | "income_incorrect"
  | "expense_incorrect"
  | "goal_outdated"
  | "transaction_miscategorized"
  | "other";
