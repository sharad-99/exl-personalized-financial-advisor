// Client-side validation mirrors the backend rules for fast feedback.
// The backend remains authoritative and re-validates everything.

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MONEY = /^\d{1,12}(\.\d{1,2})?$/;

export type FieldErrors = Record<string, string>;

export function validateLogin(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!email.trim()) errors.email = "Enter your email address.";
  else if (!EMAIL.test(email.trim()) || email.length > 254) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Enter your password.";
  else if (password.length > 128) errors.password = "Password is too long.";
  return errors;
}

export interface GoalFormValues {
  name: string;
  goal_type: string;
  target_amount: string;
  saved_amount: string;
  monthly_contribution: string;
  target_date: string;
  priority: string;
}

export const GOAL_TYPES = [
  "emergency_fund",
  "home_purchase",
  "education",
  "retirement",
  "vehicle",
  "travel",
  "wedding",
  "debt_payoff",
  "other",
] as const;

export function validateGoal(values: GoalFormValues, today: string): FieldErrors {
  const errors: FieldErrors = {};
  const name = values.name.trim();
  if (!name) errors.name = "Give the goal a name.";
  else if (name.length > 80) errors.name = "Use 80 characters or fewer.";
  if (!GOAL_TYPES.includes(values.goal_type as (typeof GOAL_TYPES)[number])) errors.goal_type = "Choose a goal type.";
  if (!MONEY.test(values.target_amount) || Number(values.target_amount) <= 0)
    errors.target_amount = "Enter a target above 0 with at most 2 decimals.";
  if (values.saved_amount && !MONEY.test(values.saved_amount)) errors.saved_amount = "Enter an amount with at most 2 decimals.";
  else if (!errors.target_amount && Number(values.saved_amount || 0) > Number(values.target_amount))
    errors.saved_amount = "Saved amount cannot exceed the target.";
  if (values.monthly_contribution && !MONEY.test(values.monthly_contribution))
    errors.monthly_contribution = "Enter an amount with at most 2 decimals.";
  if (values.target_date && values.target_date <= today) errors.target_date = "Choose a date in the future.";
  const priority = Number(values.priority);
  if (!Number.isInteger(priority) || priority < 1 || priority > 5) errors.priority = "Priority must be 1–5.";
  return errors;
}
