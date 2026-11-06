#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты ViBo Code: MCP-протокол, поиск, песочница, память, API, лимиты."""
from __future__ import annotations

import json
import subprocess
import sys

SERVER = "/opt/vibocode/vibocode/server.py"
PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def rpc(lines: list[dict]) -> list[dict]:
    payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in lines) + "\n"
    p = subprocess.run([sys.executable, SERVER], input=payload, capture_output=True,
                       text=True, timeout=90)
    out = []
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    if not out and p.stderr:
        print("STDERR:", p.stderr[-800:])
    return out


def tool(resp: dict) -> dict:
    return resp.get("result", {}).get("structuredContent", {})


print("1. Протокол MCP")
resps = rpc([
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
])
check("initialize отвечает", len(resps) >= 1 and resps[0].get("result", {}).get("serverInfo", {}).get("name") == "vibocode")
tools = resps[1]["result"]["tools"] if len(resps) > 1 else []
check("ровно 2 инструмента", len(tools) == 2, f"получено {len(tools)}")
check("инструменты search и run", {t["name"] for t in tools} == {"search", "run"})
size = len(json.dumps(tools, ensure_ascii=False))
check("каталог инструментов < 2000 символов", size < 2000, f"{size} символов")
print(f"     размер tools/list: {size} символов ≈ {size // 4} токенов")

print("2. Поиск действий и памяти")
resps = rpc([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "search", "arguments": {"query": "баланс копилки класса"}}}])
res = tool(resps[0]) if resps else {}
acts = [a["name"] for a in res.get("actions", [])]
check("нашёл действия по балансу", any("balance" in a or "class" in a for a in acts), str(acts))
check("в ответе есть память", "memories" in res)
check("ответ компактный (< 1500 символов)",
      len(json.dumps(res, ensure_ascii=False)) < 1500,
      f'{len(json.dumps(res, ensure_ascii=False))} символов')

print("3. Код в песочнице: API + память за один вызов")
code = '''
h = api.get("/api/health")
print("health:", h["status"], h["data"].get("storage"))
vi.add("health копилки", "storage=local-json, каналы выключены")
facts = vi.find("health копилки")
print("память:", len(facts), "факт(ов)")
print("статистика:", vi.stats())
'''
resps = rpc([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
              "params": {"name": "run", "arguments": {"code": code}}}])
res = tool(resps[0]) if resps else {}
check("код выполнен", res.get("ok") is True, str(res.get("error"))[:200])
check("API ответил 200", any(c.get("op") == "api.get" and c.get("status") == 200 for c in res.get("calls", [])))
check("запись в память прошла", any(c.get("op") == "vibo.add" and c.get("ok") for c in res.get("calls", [])))
check("чтение из памяти прошло", any(c.get("op") == "vibo.find" for c in res.get("calls", [])))
print("     вывод:", (res.get("output") or "").replace("\n", " | ")[:160])

print("4. Песочница блокирует опасное")
for label, bad in [
    ("импорт os", 'import os\nprint(os.listdir("/"))'),
    ("открытие файла", 'f = open("/etc/passwd")\nprint(f.read())'),
    ("eval", 'print(eval("1+1"))'),
    ("служебный атрибут", 'print(vi.__class__)'),
    ("бесконечный цикл", 'while True:\n    pass'),
    ("обращение к сети напрямую", 'import socket\nprint(socket.gethostname())'),
]:
    resps = rpc([{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                  "params": {"name": "run", "arguments": {"code": bad}}}])
    res = tool(resps[0]) if resps else {}
    check(f"заблокировано: {label}", res.get("ok") is False, str(res)[:120])

print("5. Лимит по хостам")
code2 = '''
try:
    api.get("https://example.com/")
except PermissionError as e:
    print("запрет:", e)
'''
resps = rpc([{"jsonrpc": "2.0", "id": 10, "method": "tools/call",
              "params": {"name": "run", "arguments": {"code": code2}}}])
res = tool(resps[0]) if resps else {}
check("чужой хост запрещён", "не разрешён" in (res.get("output") or ""), str(res.get("output"))[:120])

print()
print("6. Защита от дублей в памяти")
code3 = '''
print(vi.add("Состояние копилки 06.11", "health ok, хранилище local-json, каналы выключены"))
'''
resps = rpc([{"jsonrpc": "2.0", "id": 11, "method": "tools/call",
              "params": {"name": "run", "arguments": {"code": code3}}}])
res = tool(resps[0]) if resps else {}
calls = res.get("calls", [])
check("повторная запись распознана как дубль",
      any(c.get("skipped") == "дубль" for c in calls), str(calls)[:200])

print()
print(f"ИТОГО: {PASS} прошло, {FAIL} провалилось")
sys.exit(1 if FAIL else 0)
