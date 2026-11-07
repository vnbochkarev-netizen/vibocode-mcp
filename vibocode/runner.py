#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model code executor. Runs as a separate process with resource limits.

Input  — JSON: {"code": "...", "cookie": null}
Output — JSON: {"ok": bool, "output": str, "error": str, "calls": [...]}
"""
from __future__ import annotations

import contextlib
import io
import json
import resource
import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from vibocode.bridge import Api, Memory  # noqa: E402

MAX_OUTPUT = 4000

SAFE_BUILTINS = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        "print", "len", "str", "int", "float", "bool", "dict", "list", "set", "tuple",
        "range", "enumerate", "zip", "sum", "min", "max", "sorted", "abs", "round",
        "isinstance", "any", "all", "repr",
        "Exception", "ValueError", "TypeError", "KeyError", "PermissionError",
    )
}


def limit() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def main() -> None:
    limit()
    payload = json.loads(sys.stdin.read() or "{}")
    code = payload.get("code", "")
    mem = Memory()
    api = Api(cookie=payload.get("cookie"))
    out = io.StringIO()
    result = {"ok": False, "output": "", "error": "", "calls": []}
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(code, "<agent>", "exec"),
                 {"__builtins__": SAFE_BUILTINS, "vi": mem, "api": api, "json": json},
                 {})
        result["ok"] = True
    except Exception:
        tb = traceback.format_exc(limit=3)
        result["error"] = tb.strip().splitlines()[-1] if tb.strip() else "error"
    text = out.getvalue()
    result["output"] = text[:MAX_OUTPUT]
    result["calls"] = mem.calls + api.calls
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
