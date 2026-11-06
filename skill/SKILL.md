---
name: vibocode
description: "Use when an agent needs many API actions without flooding context: search finds the right endpoints, run executes model-written Python in a sandbox with memory (ViBo) and allowlisted HTTP in one call."
version: 0.1.0
tools: [python]
license: Proprietary — https://wwwvibo.com
---

# ViBo Code — два инструмента вместо каталога API

Проблема: API из десятков эндпоинтов, описанный по инструменту на каждый, съедает контекст
агента (2 500 методов Cloudflare — 1,17 млн токенов). Решение: два инструмента.

1. `search` — по запросу находит подходящие эндпоинты и факты памяти, отдаёт компактные
   сигнатуры (`class_balance: GET /api/class-balance`) вместо полных описаний.
2. `run` — исполняет Python-код модели в песочнице: `api.get(path)` только по allowlist,
   `vi.add/find/stats` для памяти ViBo. Один вызов закрывает цепочку «нашёл → вызвал → запомнил».

## Когда применять

- у сервиса десятки и сотни действий, а агент ходит в 3–4;
- нужен один вызов на цепочку запросов вместо десяти раундов;
- результат вызова надо сразу записать в память, чтобы следующая сессия не выясняла заново.

## Установка

```bash
# каталог действий сервиса
vi /opt/vibocode/catalog.json     # base_url, allow_domains, actions[]

# запуск MCP-сервера (stdio, JSON-RPC построчно)
python3 /opt/vibocode/vibocode/server.py

# тесты PoC: 19 проверок, включая блокировки песочницы
python3 /opt/vibocode/tests/test_mcp.py
```

## Использование из CLI

```bash
# что умеет сервис по этому запросу
python3 skill/scripts/vibocode.py search "баланс копилки класса"

# выполнить код в песочнице
python3 skill/scripts/vibocode.py run 'h = api.get("/api/health"); print(h["status"])'
```

## Безопасность

- импорты: только `json, math, re, datetime, statistics, itertools`;
- запрещены `open, eval, exec, compile, __import__, getattr, setattr`, служебные атрибуты,
  `global/nonlocal`, бесконечные циклы;
- сеть: только `api.get(path)` и только домены из `allow_domains`;
- лимиты: 40 с на запуск, 1,5 ГБ памяти, 20 с CPU, вывод до 4 000 символов;
- повторная запись того же факта в память пропускается (защита от дублей).

## Ограничения

- песочница уровня Python (AST + rlimits + отдельный процесс), не изолят V8;
- сессионные методы требуют cookie или сервисного токена;
- каталог статичный: новый эндпоинт добавляется в `catalog.json`.

## Проверка качества

Склонируй репозиторий ViBo-SkillQA и прогони этот каталог через скрипт проверки из его корня:

```bash
git clone https://github.com/vnbochkarev-netizen/ViBo-SkillQA.git
cd ViBo-SkillQA && python3 <скрипт-проверки> test <путь-к-этому-каталогу> --lang ru
```
