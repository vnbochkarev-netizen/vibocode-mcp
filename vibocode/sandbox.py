#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Песочница: проверка кода модели по AST и запуск в отдельном процессе с лимитами."""
from __future__ import annotations

import ast
import json
import os
import subprocess
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
        raise SandboxError(f"синтаксис: {e.msg} (строка {e.lineno})")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if m.split(".")[0] not in ALLOWED_IMPORTS:
                    raise SandboxError(f"импорт {m} запрещён (разрешены: {sorted(ALLOWED_IMPORTS)})")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"обращение к {node.id} запрещено")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise SandboxError(f"доступ к служебному атрибуту {node.attr} запрещён")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise SandboxError("global/nonlocal запрещены")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value:
            raise SandboxError("бесконечный цикл запрещён")


def run(code: str, cookie: str | None = None, timeout: int = 40) -> dict:
    try:
        validate(code)
    except SandboxError as e:
        return {"ok": False, "output": "", "error": str(e), "calls": []}
    payload = json.dumps({"code": code, "cookie": cookie}, ensure_ascii=False)
    try:
        p = subprocess.run(
            [os.environ.get("VIBOCODE_PYTHON", "/usr/bin/python3"), "-I",
             str(Path(__file__).resolve().parent / "runner.py")],
            input=payload, capture_output=True, text=True, timeout=timeout,
            cwd=str(PKG_ROOT),
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/root",
                 "PYTHONPATH": str(PKG_ROOT),
                 "VIBOCODE_CATALOG": os.environ.get("VIBOCODE_CATALOG", str(PKG_ROOT / "catalog.json")),
                 "VIBO_MEM_FILE": os.environ.get("VIBO_MEM_FILE",
                                                 "/root/.hermes/skills/vibo-memory/memory.web")},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": f"превышен лимит времени ({timeout} с)",
                "calls": []}
    if p.returncode != 0 and not p.stdout.strip():
        return {"ok": False, "output": "", "error": (p.stderr or "")[-500:], "calls": []}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "output": p.stdout[:2000], "error": "некорректный ответ песочницы",
                "calls": []}
