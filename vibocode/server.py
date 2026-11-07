#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViBo Code — an MCP server with two tools: search and run.

Transport: JSON-RPC 2.0, one object per line over stdio.
Tools:
  search — finds catalog actions and memory facts, returns compact signatures
  run    — executes model-written code in a sandbox with vi.* (memory) and api.* (allowlist)
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from vibocode import catalog, sandbox  # noqa: E402
from vibocode.bridge import Memory  # noqa: E402

PROTOCOL = "2025-06-18"
SERVER_INFO = {"name": "vibocode", "version": "0.1.3"}

TOOLS = [
    {
        "name": "search",
        "description": (
            "Find available service actions and related memory facts. "
            "Returns compact signatures (name: METHOD /path), never the full catalog. "
            "Call it before run to get the exact endpoint path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you want to do, in words"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 4},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run",
        "description": (
            "Execute Python code in a sandbox. Available: vi.find(query), vi.add(label, content), "
            "vi.stats(), api.get(path), json. One run may contain any number of calls. "
            "Allowed imports: json, math, re, datetime, statistics, itertools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["code"],
        },
    },
]


def call_tool(name: str, args: dict) -> dict:
    if name == "search":
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 4))
        actions = catalog.search(query, limit=limit)
        mem = Memory()
        facts = mem.find(query, limit=3) if len(query) > 2 else []
        lines = ["Service actions:"]
        lines += [f"  {catalog.signature(a)} — {a['desc']}" for a in actions] or ["  nothing found"]
        lines.append("Memory:")
        lines += [f"  • {f['label']}: {f['text']}" for f in facts] or ["  empty"]
        text = "\n".join(lines)
        return {"content": [{"type": "text", "text": text}],
                "structuredContent": {"actions": actions, "memories": facts}}

    if name == "run":
        code = str(args.get("code", ""))
        result = sandbox.run(code)
        body = json.dumps(result, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": body}],
                "structuredContent": result,
                "isError": not result.get("ok", False)}

    raise ValueError(f"unknown tool: {name}")


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            out = call_tool(params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": out}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": f"error: {e}"}],
                               "structuredContent": {"ok": False, "error": str(e), "calls": []},
                               "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not supported: {method}"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
