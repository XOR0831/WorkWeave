// Serves the static export in out/ like Firebase Hosting (cleanUrls + trailingSlash):
// /path/ -> out/path/index.html, unknown paths -> out/404.html with status 404.
// Local preview helper only; not a production server.
// With API_ORIGIN set (e.g. http://127.0.0.1:8000), /api/* is proxied there so the browser stays
// same-origin with the API and its HttpOnly session cookie (as a Hosting rewrite would in the cloud).
import { createServer, request as httpRequest } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const root = join(process.cwd(), process.env.STATIC_ROOT ?? "out");
const port = Number(process.env.PORT ?? 4318);
const apiOrigin = process.env.API_ORIGIN ? new URL(process.env.API_ORIGIN) : null;
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json", ".txt": "text/plain", ".ico": "image/x-icon" };

async function resolve(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
  const candidates = [join(root, clean), join(root, clean, "index.html"), join(root, `${clean}.html`)];
  for (const c of candidates) {
    if (!c.startsWith(root)) continue;
    try {
      if ((await stat(c)).isFile()) return c;
    } catch {}
  }
  return null;
}

function proxy(req, res) {
  const upstream = httpRequest(
    { hostname: apiOrigin.hostname, port: apiOrigin.port, path: req.url, method: req.method, headers: { ...req.headers, host: apiOrigin.host } },
    (r) => {
      res.writeHead(r.statusCode ?? 502, r.headers);
      r.pipe(res);
    },
  );
  upstream.on("error", () => {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ request_id: "proxy", error: { code: "DEPENDENCY_UNAVAILABLE", message: "The local WorkWeave API isn't running on " + apiOrigin.origin + ".", retryable: true } }));
  });
  req.pipe(upstream);
}

createServer(async (req, res) => {
  if (apiOrigin && (req.url === "/api" || req.url?.startsWith("/api/"))) return proxy(req, res);
  const file = await resolve(req.url ?? "/");
  if (!file) {
    res.writeHead(404, { "content-type": types[".html"] });
    res.end(await readFile(join(root, "404.html")).catch(() => "Not found"));
    return;
  }
  res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream" });
  res.end(await readFile(file));
}).listen(port, () => console.log(`Serving ${root} at http://localhost:${port}${apiOrigin ? ` (proxying /api to ${apiOrigin.origin})` : ""}`));
