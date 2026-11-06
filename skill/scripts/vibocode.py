#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViBo Code CLI: поиск действий и запуск кода в песочнице.

  vibocode.py search "<запрос>"      — сигнатуры действий и факты памяти
  vibocode.py run "<код>"            — выполнить код в песочнице
  vibocode.py run -f file.py         — выполнить код из файла
  vibocode.py tools                  — список MCP-инструментов
  vibocode.py selftest               — быстрая самопроверка
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/opt/vibocode")

from vibocode import catalog, sandbox  # noqa: E402
from vibocode.bridge import Memory  # noqa: E402


def cmd_search(query: str, limit: int) -> int:
    actions = catalog.search(query, limit=limit)
    print("Действия сервиса:")
    if actions:
        for a in actions:
            print(f"  {catalog.signature(a)} — {a['desc']}")
    else:
        print("  ничего не найдено")
    facts = Memory().find(query, limit=3)
    print("Память:")
    for f in facts:
        print(f"  • {f['label']}: {f['text']}")
    if not facts:
        print("  пусто")
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
        ("песочница считает", 'print(1 + 1)', True),
        ("импорт os запрещён", 'import os', False),
        ("открытие файла запрещено", 'open("/etc/passwd")', False),
        ("api.get работает", 'print(api.get("/api/health")["status"])', True),
        ("чужой хост запрещён", 'api.get("https://example.com/")', False),
    ]
    for name, code, expect in cases:
        got = sandbox.run(code).get("ok")
        mark = "✅" if got is expect else "❌"
        print(f"  {mark} {name}")
        ok += got is expect
    print(f"\n{ok}/{len(cases)} проверок прошло")
    return 0 if ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ViBo Code: search + run в одном инструменте")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("search", help="найти действия и факты памяти")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=4)

    p = sub.add_parser("run", help="выполнить код в песочнице")
    p.add_argument("code", nargs="?")
    p.add_argument("-f", "--file")

    sub.add_parser("tools", help="показать MCP-инструменты")
    sub.add_parser("selftest", help="быстрая самопроверка")

    args = ap.parse_args()
    if args.cmd == "search":
        return cmd_search(" ".join(args.query), args.limit)
    if args.cmd == "run":
        code = args.code
        if args.file:
            with open(args.file, encoding="utf-8") as fh:
                code = fh.read()
        if not code:
            print("нужен код: vibocode.py run '<код>' или -f file.py", file=sys.stderr)
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
