#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Action catalog: find the endpoints you need instead of describing all of them in context."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = Path(os.environ.get("VIBOCODE_CATALOG", _ROOT / "catalog.json"))
ALIASES_PATH = Path(os.environ.get("VIBOCODE_ALIASES", Path(__file__).resolve().parent / "aliases.json"))

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile("[^0-9a-z\u0430-\u044f\u0451]+")
_PARAM = re.compile(r"\{[^}]*\}")


def _load_aliases() -> tuple[dict, dict]:
    """Alias tables: intent word -> HTTP method, and noun -> catalog terms.

    Kept in aliases.json so the code stays language-agnostic: a new language is data only.
    """
    try:
        data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        return data.get("verbs", {}), data.get("nouns", {})
    except Exception:
        return {}, {}


VERBS, NOUNS = _load_aliases()


def load() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _norm(w: str) -> str:
    """Lowercase, folding one Cyrillic spelling variant so both forms match."""
    return w.replace("\u0451", "\u0435").lower()


def _tokens(text: str) -> list[str]:
    """PostPaymentIntents -> [post, payment, intents]; /v1/payment_intents -> [v1, payment, intents]."""
    return [t for t in _WORD.split(_norm(_CAMEL.sub(" ", text))) if t]


def _same(a: str, b: str) -> bool:
    """Equality tolerant to English plurals: subscription == subscriptions."""
    if a == b:
        return True
    sa, sb = (a[:-1] if a.endswith("s") else a), (b[:-1] if b.endswith("s") else b)
    if sa == sb:
        return True
    return a.endswith(b + "s") or b.endswith(a + "s")


def _query_terms(query: str) -> tuple[list[str], set[str]]:
    q = _norm(query)
    terms: list[str] = []
    methods: set[str] = set()

    for word, en in sorted(NOUNS.items(), key=lambda kv: -len(kv[0])):  # multi-word first
        if " " in word and word in q:
            terms.extend(en)
            q = q.replace(word, " ")

    for raw in _WORD.split(q):
        if len(raw) < 2:
            continue
        if raw in VERBS:
            methods.add(VERBS[raw])
            continue
        if raw in NOUNS:
            terms.extend(NOUNS[raw])
            continue
        stem = raw[:5]
        hit = [en for word, en in NOUNS.items() if " " not in word and word.startswith(stem)]
        if hit:
            for en in hit:
                terms.extend(en)
            continue
        terms.append(raw)
    return list(dict.fromkeys(terms)), methods


def _score(query: str, action: dict) -> int:
    terms, methods = _query_terms(query)
    if not terms and not methods:
        return 0

    name_toks = _tokens(action.get("name", ""))
    path = action.get("path", "")
    # resource segments only: no version, no parameters. /v1/charges/{charge}/refund -> charges/refund
    res_toks = [t for t in _tokens(_PARAM.sub(" ", path)) if not re.fullmatch(r"v\d+|\d+", t)]
    resource = "/".join(res_toks)
    first, last = (res_toks[0] if res_toks else ""), (res_toks[-1] if res_toks else "")
    desc = _norm(action.get("desc", ""))

    score = 0
    for t in terms:
        if any(_same(tok, t) for tok in name_toks):
            score += 7
        elif any(tok.startswith(t[:4]) for tok in name_toks) and len(t) >= 4:
            score += 4
        if any(tok.startswith(t[:4]) for tok in res_toks) and len(t) >= 4:
            score += 3
        if t in desc or (len(t) >= 4 and t[:5] in desc):
            score += 2
    if not score:
        return 0

    if methods:
        score += 6 if action.get("method") in methods else -3

    # hitting the resource itself beats hitting it somewhere deep in the path
    for t in terms:
        if _same(first, t) or _same(last, t):
            score += 10
        elif first.startswith(t[:4]) or last.startswith(t[:4]):
            score += 6
        elif t[:4] in resource:
            score += 2
    # a deep path is usually a sub-resource, not what was asked for
    score -= 2 * max(0, len(res_toks) - 1)
    return score


def search(query: str, limit: int = 4) -> list[dict]:
    cat = load()
    scored = [(s, a) for a in cat["actions"] if (s := _score(query, a)) > 0]
    scored.sort(key=lambda x: (-x[0], len(x[1].get("path", ""))))
    return [a for _, a in scored[:limit]]


def signature(action: dict) -> str:
    """Compact signature for the model: no descriptions, only what a call needs."""
    auth = "" if action.get("auth") is False else " (auth required)"
    return f'{action["name"]}: {action["method"]} {action["path"]}{auth}'


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "balance"
    for a in search(q):
        print(signature(a), "—", a["desc"])
