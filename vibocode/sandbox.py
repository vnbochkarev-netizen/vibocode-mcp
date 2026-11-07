#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sandbox: AST validation of model code, then execution in a separate process with limits."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_IMPORTS = {"json", "math", "re", "datetime", "statistics", "itertools"}
FORBIDDEN_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
    "dir", "getattr", "setattr", "delattr", "input", "breakpoint", "memoryview",
}


class SandboxError(Exception):
    pass


def validate(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"syntax error: {e.msg} (line {e.lineno})")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if m.split(".")[0] not in ALLOWED_IMPORTS:
                    raise SandboxError(f"import {m} is not allowed (allowed: {sorted(ALLOWED_IMPORTS)})")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"{node.id} is not allowed")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise SandboxError(f"access to internal attribute {node.attr} is not allowed")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise SandboxError("global/nonlocal is not allowed")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value:
            raise SandboxError("infinite loop is not allowed")


def run(code: str, cookie: str | None = None, timeout: int = 40) -> dict:
    try:
        validate(code)
    except SandboxError as e:
        return {"ok": False, "output": "", "error": str(e), "calls": []}
    payload = json.dumps({"code": code, "cookie": cookie}, ensure_ascii=False)
    child_env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                 "HOME": os.environ.get("HOME", os.path.expanduser("~")),
                 "PYTHONPATH": str(PKG_ROOT),
                 "VIBOCODE_CATALOG": os.environ.get("VIBOCODE_CATALOG", str(PKG_ROOT / "catalog.json")),
                 "VIBO_MEM_FILE": os.environ.get("VIBO_MEM_FILE",
                                                 os.path.expanduser("~/.vibo/memory.web"))}
    # only forward VIBO_HOME when the user set it: otherwise the bridge picks the installation
    if os.environ.get("VIBO_HOME"):
        child_env["VIBO_HOME"] = os.environ["VIBO_HOME"]
    try:
        p = subprocess.run(
            [os.environ.get("VIBOCODE_PYTHON", sys.executable), "-I",
             str(Path(__file__).resolve().parent / "runner.py")],
            input=payload, capture_output=True, text=True, timeout=timeout,
            cwd=str(PKG_ROOT),
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": f"time limit exceeded ({timeout} s)",
                "calls": []}
    if p.returncode != 0 and not p.stdout.strip():
        return {"ok": False, "output": "", "error": (p.stderr or "")[-500:], "calls": []}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "output": p.stdout[:2000], "error": "invalid sandbox response",
                "calls": []}
