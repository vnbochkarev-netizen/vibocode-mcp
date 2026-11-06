# vibocode-mcp

**Два инструмента вместо каталога API.** MCP-сервер, который держит контекст агента маленьким,
а руки — длинными.

```
search  — находит нужные эндпоинты и факты памяти, отдаёт компактные сигнатуры
run     — исполняет Python-код модели в песочнице: api.get(path) + vi.add/find/stats
```

Вся палитра инструментов — **219 токенов**. Полный каталог сервиса в обычном виде — 425 токенов
на 12 эндпоинтах; на сотнях разница становится кратной.

## Установка

```bash
npx vibocode-mcp
```

Нужен **Node 18+** и **Python 3.10+** (сервер на Python).

Конфигурация MCP-клиента:

```json
{
  "mcpServers": {
    "vibocode": {
      "command": "npx",
      "args": ["-y", "vibocode-mcp"],
      "env": {
        "VIBOCODE_CATALOG": "/путь/к/catalog.json",
        "VIBO_MEM_FILE": "/путь/к/memory.web"
      }
    }
  }
}
```

## Каталог действий

`catalog.json` описывает сервис: базовый URL, разрешённые домены и список действий.

```json
{
  "service": "klasskopilka",
  "base_url": "http://127.0.0.1:4174",
  "allow_domains": ["127.0.0.1"],
  "actions": [
    {"name": "health", "method": "GET", "path": "/api/health", "auth": false,
     "desc": "Состояние сервиса"}
  ]
}
```

Каталог не пишется руками: для OpenAPI он собирается генератором.

```bash
python3 tools/openapi_to_catalog.py openapi.json -o catalog.json \
  --base-url https://api.example.com --allow api.example.com --service example
```

## Как это выглядит в работе

```python
h = api.get("/api/health")
print(h["status"], h["data"]["storage"])
vi.add("Состояние копилки", "health ok, хранилище local-json")
print(vi.stats())
```

Один `run` — запрос к API, запись в память, чтение статистики. Без памяти это просто песочница:
ценность в том, что следующая сессия не выясняет заново то, что уже выяснено.

## Что внутри

```
bin/vibocode-mcp.js      — точка входа npm-пакета (запускает Python-сервер)
vibocode/server.py       — MCP-сервер (JSON-RPC по stdio)
vibocode/catalog.py      — поиск по каталогу, компактные сигнатуры
vibocode/bridge.py       — мост: память ViBo + HTTP по allowlist
vibocode/sandbox.py      — проверка AST + запуск в отдельном процессе с лимитами
vibocode/runner.py       — исполнитель кода модели
tools/openapi_to_catalog.py — генератор каталога из OpenAPI
tests/test_mcp.py        — 19 проверок
skill/                   — оформление как скилла (SKILL.md + CLI)
```

## Безопасность

- импорты: `json, math, re, datetime, statistics, itertools`
- запрещены `open, eval, exec, compile, __import__, getattr, setattr`, служебные атрибуты,
  `global/nonlocal`, бесконечные циклы
- сеть: только `api.get(path)` и только домены из `allow_domains`
- лимиты: 40 с, 1,5 ГБ памяти, 20 с CPU, вывод до 4 000 символов
- повторная запись того же факта в память пропускается

Это песочница уровня Python (AST + rlimits + отдельный процесс), а не изолят V8: она защищает
от случайного и небрежного кода, но не от целенаправленной атаки на уровне ОС.

## Тесты

```bash
python3 tests/test_mcp.py     # протокол, поиск, память, API, лимиты, блокировки
```

## Замеры

- `tools/list` (оба инструмента): 876 символов ≈ 219 токенов
- Полный каталог из 12 действий обычными инструментами: 1 702 символа ≈ 425 токенов
- На 12 эндпоинтах выигрыш двукратный, дальше растёт линейно

## Ограничения

- транспорт — JSON-RPC построчно (не Content-Length), для stdio-клиентов достаточно
- сессионные методы требуют cookie или сервисного токена
- каталог статичный: новые эндпоинты добавляются в `catalog.json` (или генератором из OpenAPI)

## Лицензия

MIT. Память ViBo — отдельный продукт со своей лицензией.
