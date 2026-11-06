#!/usr/bin/env node
// vibocode-mcp — MCP-сервер: два инструмента (search + run) вместо каталога API.
// Обёртка запускает Python-сервер и пробрасывает stdio без изменений.
const { spawn } = require("node:child_process");
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
      const { status } = require("node:child_process").spawnSync(c, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"]);
      if (status === 0) return c;
    } catch (_) { /* пробуем следующий */ }
  }
  return null;
}

if (!fs.existsSync(serverPy)) {
  console.error(`vibocode-mcp: не найден сервер ${serverPy}`);
  process.exit(1);
}

const python = findPython();
if (!python) {
  console.error("vibocode-mcp: нужен Python 3.10+ (проверьте `python3 -V` или задайте VIBOCODE_PYTHON)");
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

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);

child.on("exit", (code) => process.exit(code === null ? 0 : code));
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
