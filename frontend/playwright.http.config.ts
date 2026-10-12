import { defineConfig, devices } from "@playwright/test";

/**
 * HTTP-mode end-to-end run: real FastAPI + PostgreSQL (disposable workweave_test database).
 * Build first: `npm run build:http`. Ports differ from the dev servers (API 8100, site 4320).
 */
export default defineConfig({
  testDir: "./tests/e2e-http",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: { baseURL: "http://localhost:4320", trace: "retain-on-failure" },
  projects: [{ name: "http-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } } }],
  webServer: [
    {
      command: "cd ../backend && uv run python -m tests.prepare_db && POSTGRES_DB=workweave_test TUTOR_ENGINE=none COMPANION_ENGINE=none HANDOVER_ENGINE=none EXIT_KT_ENGINE=none NOTIFICATIONS=none DISPATCHER_IN_PROCESS=false AUTO_ASSIGN_WORK=false INGESTION_PYTHON= LOCAL_STORAGE_DIR=/tmp/workweave-e2e-storage GEMINI_API_KEY= GEMINI_EVALUATOR_API_KEY= uv run uvicorn app.main:app --host 127.0.0.1 --port 8100",
      url: "http://127.0.0.1:8100/api/health",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "STATIC_ROOT=out-http API_ORIGIN=http://127.0.0.1:8100 PORT=4320 node scripts/serve-static.mjs",
      url: "http://localhost:4320/demo/",
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
