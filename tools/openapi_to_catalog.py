#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAPI -> catalog.json for ViBo Code.

Usage:
    python3 openapi_to_catalog.py openapi.json -o catalog.json \
        --base-url https://api.example.com --allow api.example.com \
        --service example --max 200

Why it matters: a hand-written catalog survives while there are a dozen endpoints.
At two hundred they are generated, otherwise the product does not scale.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_DESC = 140


def short(text: str, limit: int = MAX_DESC) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pick_base(spec: dict) -> str:
    for srv in spec.get("servers") or []:
        url = srv.get("url", "")
        if url:
            return url.rstrip("/")
    return ""


def convert(spec: dict, limit: int) -> list[dict]:
    actions: list[dict] = []
    for path, ops in (spec.get("paths") or {}).items():
        if not isinstance(ops, dict):
            continue
        path_params = ops.get("parameters") or []
        for method, op in ops.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, dict):
                continue
            name = op.get("operationId") or re.sub(r"[^a-z0-9]+", "_", f"{method}_{path}".lower()).strip("_")
            params = list(path_params) + list(op.get("parameters") or [])
            has_body = bool(op.get("requestBody"))
            desc = short(op.get("description") or op.get("summary") or "")
            if params or has_body:
                parts = []
                if params:
                    parts.append("params: " + ", ".join(
                        p.get("name", "") for p in params if isinstance(p, dict)))
                if has_body:
                    parts.append("request body")
                desc = (desc + " · " if desc else "") + "; ".join(parts)
            actions.append({
                "name": name,
                "method": method.upper(),
                "path": path,
                "auth": bool(op.get("security")),
                "desc": short(desc),
            })
            if len(actions) >= limit:
                return actions
    return actions


def main() -> int:
    ap = argparse.ArgumentParser(description="Build catalog.json from an OpenAPI spec")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", default="catalog.json")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--allow", default="", help="comma-separated domains")
    ap.add_argument("--service", default="service")
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    actions = convert(spec, args.max)
    base = args.base_url or pick_base(spec)
    host = re.sub(r"^https?://", "", base).split("/")[0]
    allow = [h.strip() for h in args.allow.split(",") if h.strip()] or ([host] if host else [])

    out = {"service": args.service, "base_url": base, "allow_domains": allow, "actions": actions}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: {args.out} — {len(actions)} actions, domains {allow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
