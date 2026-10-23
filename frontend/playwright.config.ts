import { defineConfig } from "@playwright/test";

// End-to-end journey against locally running services (see docs/testing.md):
//   backend on :8000 (seeded synthetic data) and frontend on :3000.
// Uses the locally installed Chrome so no browser download is required;
// CI sets E2E_BROWSER_CHANNEL="" to use Playwright's bundled Chromium.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: process.env.E2E_BROWSER_CHANNEL ?? "chrome",
    headless: true,
    trace: "retain-on-failure",
  },
});
