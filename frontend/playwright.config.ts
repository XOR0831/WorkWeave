import { defineConfig, devices } from "@playwright/test";

// E2E runs against the real static export (`npm run build` first), served like Firebase Hosting.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:4318", trace: "retain-on-failure" },
  webServer: { command: "node scripts/serve-static.mjs", url: "http://localhost:4318/", reuseExistingServer: true },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } }, testIgnore: /responsive\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /responsive\.spec\.ts/ },
  ],
});
