#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViBo Code tests: MCP protocol, search, sandbox, memory, API, limits.

Self-contained: starts a local HTTP service on a free port and a temporary catalog,
so it runs on a fresh clone with no external dependencies.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = str(ROOT / "vibocode" / "server.py")
PASS, FAIL, SKIP = 0, 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def skip(name: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  SKIP {name} ({why})")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"ok": True, "storage": "local-json", "path": self.path}).encode()
        self.send_response(200 if self.path.startswith("/api/") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> int:
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    tmp = Path(tempfile.mkdtemp(prefix="vibocode-test-"))
    catalog = tmp / "catalog.json"
    catalog.write_text(json.dumps({
        "service": "test", "base_url": f"http://127.0.0.1:{port}",
        "allow_domains": ["127.0.0.1"],
        "actions": [
            {"name": "health", "method": "GET", "path": "/api/health", "auth": False,
             "desc": "Service health"},
            {"name": "group_balance", "method": "GET", "path": "/api/group-balance", "auth": True,
             "desc": "Group balance: collected, spent, remaining"},
            {"name": "items", "method": "GET", "path": "/api/items", "auth": True,
             "desc": "Items list"},
        ],
    }), encoding="utf-8")

    env = dict(os.environ)
    env["VIBOCODE_CATALOG"] = str(catalog)
    env["VIBO_MEM_FILE"] = str(tmp / "memory.web")
    memory_on = any((Path(p) / "vibo-cli").exists() for p in (
        env.get("VIBO_HOME") or "",
        str(Path.home() / ".vibo"),
        str(Path.home() / ".hermes/skills/vibo-memory"),
    ) if p)

    def rpc(lines: list[dict]) -> list[dict]:
        payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in lines) + "\n"
        p = subprocess.run([sys.executable, SERVER], input=payload, capture_output=True,
                           text=True, timeout=90, env=env)
        out = []
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                out.append(json.loads(line))
        if not out and p.stderr:
            print("STDERR:", p.stderr[-800:])
        return out

    def tool(resp: dict) -> dict:
        return resp.get("result", {}).get("structuredContent", {})

    print("1. MCP protocol")
    resps = rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    check("initialize responds",
          len(resps) >= 1 and resps[0].get("result", {}).get("serverInfo", {}).get("name") == "vibocode")
    tools = resps[1]["result"]["tools"] if len(resps) > 1 else []
    check("exactly two tools", len(tools) == 2, f"got {len(tools)}")
    check("tools are search and run", {t["name"] for t in tools} == {"search", "run"})
    size = len(json.dumps(tools, ensure_ascii=False))
    check("tools/list under 2000 characters", size < 2000, f"{size} characters")
    print(f"       tools/list size: {size} characters")

    print("2. Search over actions and memory")
    resps = rpc([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "search", "arguments": {"query": "group balance"}}}])
    res = tool(resps[0]) if resps else {}
    acts = [a["name"] for a in res.get("actions", [])]
    check("found balance actions", any("balance" in a for a in acts), str(acts))
    check("memory section present", "memories" in res)
    check("response is compact (< 1500 characters)",
          len(json.dumps(res, ensure_ascii=False)) < 1500,
          f'{len(json.dumps(res, ensure_ascii=False))} characters')

    print("3. Sandbox: API + memory in one call")
    code = '''
h = api.get("/api/health")
print("health:", h["status"], h["data"].get("storage"))
vi.add("service health", "storage=local-json, channels off")
facts = vi.find("service health")
print("memory:", len(facts), "fact(s)")
print("stats:", vi.stats())
'''
    resps = rpc([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                  "params": {"name": "run", "arguments": {"code": code}}}])
    res = tool(resps[0]) if resps else {}
    check("code executed", res.get("ok") is True, str(res.get("error"))[:200])
    check("API answered 200",
          any(c.get("op") == "api.get" and c.get("status") == 200 for c in res.get("calls", [])))
    if memory_on:
        check("memory write ok",
              any(c.get("op") == "vibo.add" and c.get("ok") for c in res.get("calls", [])))
        check("memory read ok", any(c.get("op") == "vibo.find" for c in res.get("calls", [])))
    else:
        skip("memory write ok", "no ViBo installation")
        skip("memory read ok", "no ViBo installation")
    print("       output:", (res.get("output") or "").replace("\n", " | ")[:160])

    print("4. Sandbox blocks dangerous code")
    for label, bad in [
        ("import os", 'import os\nprint(os.listdir("/"))'),
        ("file open", 'f = open("/etc/passwd")\nprint(f.read())'),
        ("eval", 'print(eval("1+1"))'),
        ("dunder attribute", 'print(vi.__class__)'),
        ("infinite loop", 'while True:\n    pass'),
        ("direct network", 'import socket\nprint(socket.gethostname())'),
    ]:
        resps = rpc([{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                      "params": {"name": "run", "arguments": {"code": bad}}}])
        res = tool(resps[0]) if resps else {}
        check(f"blocked: {label}", res.get("ok") is False, str(res)[:120])

    print("5. Host allowlist")
    code2 = '''
try:
    api.get("https://example.com/")
except PermissionError as e:
    print("denied:", e)
'''
    resps = rpc([{"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                  "params": {"name": "run", "arguments": {"code": code2}}}])
    res = tool(resps[0]) if resps else {}
    check("foreign host denied", "is not allowed" in (res.get("output") or ""),
          str(res.get("output"))[:120])

    print()
    print("6. Memory duplicate protection")
    code3 = '''
print(vi.add("service state", "health ok, storage local-json, channels off"))
print(vi.add("service state", "health ok, storage local-json, channels off"))
'''
    resps = rpc([{"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                  "params": {"name": "run", "arguments": {"code": code3}}}])
    res = tool(resps[0]) if resps else {}
    calls = res.get("calls", [])
    if memory_on:
        check("repeated write detected as duplicate",
              any(c.get("skipped") == "duplicate" for c in calls), str(calls)[:200])
    else:
        skip("repeated write detected as duplicate", "no ViBo installation")

    httpd.shutdown()
    print()
    print(f"TOTAL: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
