// Static file server for the ClusterNet landing page.
//
// Zero dependencies on purpose: only Node's built-in modules are used, so the
// Specific build installs nothing and the image stays tiny. Specific injects
// PORT, and the public endpoint is routed to that port.

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)));
const PORT = Number(process.env.PORT) || 3000;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

function send(res, status, body, type = "text/plain; charset=utf-8") {
  res.writeHead(status, { "content-type": type });
  res.end(body);
}

const server = createServer(async (req, res) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    send(res, 405, "Method not allowed");
    return;
  }

  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
  } catch {
    send(res, 400, "Bad request");
    return;
  }

  // Map "/" and any bare directory-like path to index.html.
  if (pathname.endsWith("/")) pathname += "index.html";

  const filePath = resolve(join(ROOT, "." + pathname));
  if (filePath !== ROOT && !filePath.startsWith(ROOT + sep)) {
    send(res, 403, "Forbidden");
    return;
  }

  let target = filePath;
  try {
    if ((await stat(target)).isDirectory()) target = join(target, "index.html");
  } catch {
    send(res, 404, "Not found");
    return;
  }

  try {
    const body = await readFile(target);
    const type = MIME[extname(target).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, {
      "content-type": type,
      "cache-control": "public, max-age=300",
    });
    res.end(req.method === "HEAD" ? undefined : body);
  } catch {
    send(res, 404, "Not found");
  }
});

server.listen(PORT, () => {
  console.log(`ClusterNet landing page listening on http://localhost:${PORT}`);
});
