// Local development: FastAPI (auto-reload) + `next dev` in API mode, in one terminal.
// Ctrl+C stops both. Needs the local PostgreSQL stack running (see ../backend/README.md).
import { spawn } from "node:child_process";
import { join } from "node:path";

const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.PORT ?? "3000";
const backend = join(process.cwd(), "..", "backend");

const procs = [
  ["api", "uv", ["run", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", apiPort], { cwd: backend }],
  ["web", "npx", ["next", "dev", "--port", webPort], { env: { ...process.env, NEXT_PUBLIC_WORKWEAVE_MODE: "http", API_ORIGIN: `http://127.0.0.1:${apiPort}` } }],
].map(([name, cmd, args, opts]) => {
  const p = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], ...opts });
  const tag = (chunk) => chunk.toString().split("\n").filter(Boolean).forEach((l) => console.log(`[${name}] ${l}`));
  p.stdout.on("data", tag);
  p.stderr.on("data", tag);
  p.on("exit", (code) => {
    console.log(`[${name}] exited (${code}); stopping the other process`);
    shutdown();
  });
  return p;
});

let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  for (const p of procs) if (p.exitCode === null) p.kill("SIGTERM");
  setTimeout(() => process.exit(0), 500);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
console.log(`WorkWeave dev stack: site http://localhost:${webPort}/demo/  ·  API http://127.0.0.1:${apiPort}/api/health`);
