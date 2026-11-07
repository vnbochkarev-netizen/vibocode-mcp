#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViBo Code CLI: search actions and run code in the sandbox.

  vibocode.py search "<query>"       — action signatures and memory facts
  vibocode.py run "<code>"           — execute code in the sandbox
  vibocode.py run -f file.py         — execute code from a file
  vibocode.py tools                  — list MCP tools
  vibocode.py selftest               — quick self-check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from vibocode import catalog, sandbox  # noqa: E402
from vibocode.bridge import Memory  # noqa: E402


def cmd_search(query: str, limit: int) -> int:
    actions = catalog.search(query, limit=limit)
    print("Service actions:")
    if actions:
        for a in actions:
            print(f"  {catalog.signature(a)} — {a['desc']}")
    else:
        print("  nothing found")
    facts = Memory().find(query, limit=3)
    print("Memory:")
    for f in facts:
        print(f"  • {f['label']}: {f['text']}")
    if not facts:
        print("  empty")
    return 0


def cmd_run(code: str) -> int:
    result = sandbox.run(code)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result.get("ok") else 1


def cmd_tools() -> int:
    from vibocode.server import TOOLS
    print(json.dumps(TOOLS, ensure_ascii=False, indent=1))
    return 0


def cmd_selftest() -> int:
    ok = 0
    cases = [
        ("sandbox computes", 'print(1 + 1)', True),
        ("import os blocked", 'import os', False),
        ("file open blocked", 'open("/etc/passwd")', False),
        ("api.get works", 'print(api.get("/api/health")["status"])', True),
        ("foreign host blocked", 'api.get("https://example.com/")', False),
    ]
    for name, code, expect in cases:
        got = sandbox.run(code).get("ok")
        mark = "OK  " if got is expect else "FAIL"
        print(f"  {mark} {name}")
        ok += got is expect
    print(f"\n{ok}/{len(cases)} checks passed")
    return 0 if ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ViBo Code: search + run in one tool")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("search", help="find actions and memory facts")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=4)

    p = sub.add_parser("run", help="execute code in the sandbox")
    p.add_argument("code", nargs="?")
    p.add_argument("-f", "--file")

    sub.add_parser("tools", help="show MCP tools")
    sub.add_parser("selftest", help="quick self-check")

    args = ap.parse_args()
    if args.cmd == "search":
        return cmd_search(" ".join(args.query), args.limit)
    if args.cmd == "run":
        code = args.code
        if args.file:
            with open(args.file, encoding="utf-8") as fh:
                code = fh.read()
        if not code:
            print("code required: vibocode.py run '<code>' or -f file.py", file=sys.stderr)
            return 2
        return cmd_run(code)
    if args.cmd == "tools":
        return cmd_tools()
    if args.cmd == "selftest":
        return cmd_selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
