import { expect, test } from "@playwright/test";

// Requires E2E_PASSWORD = LOCAL_DEMO_PASSWORD of the running backend (synthetic demo users only).
const password = process.env.E2E_PASSWORD ?? "";

test.skip(!password, "Set E2E_PASSWORD to run the end-to-end journey");

const nav = (page: import("@playwright/test").Page) => page.getByRole("navigation", { name: "Main" });

async function signIn(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test("unauthenticated visitors are sent to login", async ({ page }) => {
  await page.goto("/insights");
  await expect(page).toHaveURL(/\/login\?next=%2Finsights/);
});

test("wrong password shows an error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("customer05@demo.exl.test");
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" })).toBeVisible();
});

test("customer journey: dashboard, money coach, feedback, goals, sign out", async ({ page }) => {
  await signIn(page, "customer43@demo.exl.test"); // debt-stressed persona: always has open advice
  await expect(page.getByRole("heading", { name: "Your financial dashboard" })).toBeVisible();
  await expect(page.getByText("Avg monthly income")).toBeVisible();
  await expect(page.getByText("Simulated data environment")).toBeVisible();

  await nav(page).getByRole("link", { name: "Money coach" }).click();
  await expect(page.getByRole("heading", { name: "Money coach" })).toBeVisible();
  const firstCard = page.locator("article").first();
  await expect(firstCard).toBeVisible();
  await firstCard.getByRole("button", { name: /Show the numbers/ }).click();
  await expect(firstCard.getByText("Calculations")).toBeVisible();
  const dismiss = firstCard.getByRole("button", { name: "Dismiss" });
  await dismiss.click();
  await firstCard.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByRole("status").filter({ hasText: /marked as dismissed/i }).first()).toBeVisible();

  await nav(page).getByRole("link", { name: "Goals" }).click();
  await page.getByRole("button", { name: "New goal" }).click();
  const goalName = `E2E Bicycle ${Date.now() % 100000}`;
  await page.getByLabel("Goal name").fill(goalName);
  await page.getByLabel("Target amount (₹)").fill("25000");
  await page.getByRole("button", { name: "Create goal" }).click();
  await expect(page.getByRole("heading", { name: goalName })).toBeVisible();

  await nav(page).getByRole("link", { name: "History" }).click();
  await page.getByRole("tab", { name: "Dismissed" }).click();
  await expect(page.locator("article").first()).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/login/);
});

test("advisor is read-only", async ({ page }) => {
  await signIn(page, "advisor@demo.exl.test");
  await expect(page.getByText("Advisor (read-only)")).toBeVisible();
  await nav(page).getByRole("link", { name: "Goals" }).click();
  await expect(page.getByRole("button", { name: "New goal" })).toHaveCount(0);
});
