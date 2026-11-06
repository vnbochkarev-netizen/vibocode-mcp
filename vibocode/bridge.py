#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мост между песочницей и внешним миром: память ViBo и API по allowlist."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request

VIBO_DIR = os.environ.get("VIBO_HOME", "/root/.hermes/skills/vibo-memory")
VIBO_CLI = os.path.join(VIBO_DIR, "vibo-cli")
VIBO_MEM = os.environ.get("VIBO_MEM_FILE", os.path.join(VIBO_DIR, "memory.web"))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = json.loads(open(os.environ.get("VIBOCODE_CATALOG", os.path.join(_ROOT, "catalog.json")),
                          encoding="utf-8").read())


class Memory:
    """Доступ к ViBo для кода, который пишет модель."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def _run(self, *args: str, timeout: int = 25) -> str:
        env = dict(os.environ)
        env["VIBO_MEM_FILE"] = VIBO_MEM
        p = subprocess.run([VIBO_CLI, *args], capture_output=True, text=True,
                           env=env, timeout=timeout, cwd=VIBO_DIR)
        return (p.stdout or "") + (p.stderr or "")

    def add(self, label: str, content: str, dedupe: bool = True) -> str:
        if dedupe:
            existing = self.find(label, limit=10)
            if any(content.strip().lower() == f["text"].strip().lower() for f in existing):
                self.calls.append({"op": "vibo.add", "label": label, "ok": True, "skipped": "дубль"})
                return "уже в памяти, запись пропущена"
        out = self._run("add", label, content)
        self.calls.append({"op": "vibo.add", "label": label, "ok": "Added" in out})
        return out.strip().splitlines()[-1] if out.strip() else ""

    def find(self, query: str, limit: int = 5) -> list[dict]:
        out = self._run("find", query)
        self.calls.append({"op": "vibo.find", "query": query})
        facts = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("•"):
                body = line.lstrip("•").strip()
                label, _, text = body.partition(":")
                facts.append({"label": label.strip(), "text": text.strip()})
            if len(facts) >= limit:
                break
        return facts

    def stats(self) -> str:
        out = self._run("stats")
        self.calls.append({"op": "vibo.stats"})
        for line in out.splitlines():
            if line.strip().startswith("Nodes"):
                return line.strip()
        return out.strip()[:200]


class Api:
    """HTTP только к разрешённым хостам из каталога."""

    def __init__(self, cookie: str | None = None) -> None:
        self.base = CATALOG["base_url"].rstrip("/")
        self.allow = set(CATALOG.get("allow_domains", []))
        self.cookie = cookie
        self.calls: list[dict] = []

    def _check(self, path: str) -> str:
        full = self.base + path if path.startswith("/") else path
        host = urllib.parse.urlparse(full).hostname or ""
        if host not in self.allow:
            raise PermissionError(f"хост {host} не разрешён (allowlist: {sorted(self.allow)})")
        return full

    def get(self, path: str, timeout: int = 8) -> dict:
        full = self._check(path)
        req = urllib.request.Request(full, headers={"Accept": "application/json"})
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                code = r.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            code = e.code
        self.calls.append({"op": "api.get", "path": path, "status": code})
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body[:500]}
        return {"status": code, "data": data}
