#!/usr/bin/env node
// vibocode-mcp — an MCP server with two tools (search + run) instead of an API catalog.
// This wrapper starts the Python server and passes stdio through unchanged.
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const pkgRoot = path.resolve(__dirname, "..");
const serverPy = path.join(pkgRoot, "vibocode", "server.py");

function findPython() {
  const candidates = [
    process.env.VIBOCODE_PYTHON,
    process.env.PYTHON,
    "python3",
    "python",
  ].filter(Boolean);
  for (const c of candidates) {
    try {
      const { status } = spawnSync(c, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"]);
      if (status === 0) return c;
    } catch (_) { /* try the next candidate */ }
  }
  return null;
}

if (!fs.existsSync(serverPy)) {
  console.error(`vibocode-mcp: server not found at ${serverPy}`);
  process.exit(1);
}

const python = findPython();
if (!python) {
  console.error("vibocode-mcp: Python 3.10+ is required (check `python3 -V` or set VIBOCODE_PYTHON)");
  process.exit(1);
}

const child = spawn(python, ["-u", serverPy], {
  cwd: pkgRoot,
  env: {
    ...process.env,
    PYTHONPATH: pkgRoot,
    PYTHONIOENCODING: "utf-8",
    VIBOCODE_CATALOG: process.env.VIBOCODE_CATALOG || path.join(pkgRoot, "catalog.json"),
  },
  stdio: ["pipe", "pipe", "inherit"],
});

child.on("error", (err) => {
  console.error(`vibocode-mcp: failed to start the server: ${err.message}`);
  process.exit(1);
});

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);

child.on("exit", (code) => process.exit(code === null ? 0 : code));
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
