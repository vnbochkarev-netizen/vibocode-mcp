#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Каталог действий: поиск нужных эндпоинтов вместо описания всех в контексте."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = Path(os.environ.get("VIBOCODE_CATALOG", _ROOT / "catalog.json"))


def load() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _score(query: str, action: dict) -> int:
    q = query.lower().strip()
    words = [w for w in re.split(r"[^0-9a-zа-яё]+", q) if len(w) > 2]
    hay = " ".join([
        action.get("name", ""),
        action.get("path", ""),
        action.get("desc", ""),
    ]).lower()
    if not words:
        return 1 if q and q in hay else 0
    score = 0
    for w in words:
        if w in hay:
            score += 3 if w in action.get("name", "").lower() else 1
        # грубая поддержка русского усечения: первые 5 символов
        elif len(w) >= 5 and w[:5] in hay:
            score += 1
    return score


def search(query: str, limit: int = 4) -> list[dict]:
    cat = load()
    scored = [(s, a) for a in cat["actions"] if (s := _score(query, a)) > 0]
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]


def signature(action: dict) -> str:
    """Компактная сигнатура для модели: без описаний, только то, что нужно для вызова."""
    auth = "" if action.get("auth") is False else " (нужна сессия)"
    return f'{action["name"]}: {action["method"]} {action["path"]}{auth}'


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "баланс"
    for a in search(q):
        print(signature(a), "—", a["desc"])
