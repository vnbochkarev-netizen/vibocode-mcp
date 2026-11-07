# vibocode-mcp

**Two tools instead of an API catalog.** An MCP server that keeps the agent's context small
and its reach long.

```
search  — finds the right endpoints and memory facts, returns compact signatures
run     — executes model-written Python in a sandbox: api.get(path) + vi.add/find/stats
```

The whole toolset is **217 tokens** (o200k_base tokenizer). The same GitHub REST catalog —
1,272 endpoints — costs **79,525 tokens** as plain MCP tools: a 366x difference. Slack's
174 endpoints: 42x. Measurements and reproduction commands are in [Benchmarks](#benchmarks).

## Install

```bash
npx vibocode-mcp
```

Requires **Node 18+** and **Python 3.10+** (the server is Python).

MCP client configuration:

```json
{
  "mcpServers": {
    "vibocode": {
      "command": "npx",
      "args": ["-y", "vibocode-mcp"],
      "env": {
        "VIBOCODE_CATALOG": "/path/to/catalog.json",
        "VIBO_MEM_FILE": "/path/to/memory.web"
      }
    }
  }
}
```

## Action catalog

`catalog.json` describes a service: base URL, allowed domains and the list of actions.

```json
{
  "service": "example",
  "base_url": "http://127.0.0.1:4174",
  "allow_domains": ["127.0.0.1"],
  "actions": [
    {"name": "health", "method": "GET", "path": "/api/health", "auth": false,
     "desc": "Service health: storage, notification channels, server time"}
  ]
}
```

The catalog is not written by hand: for OpenAPI it is generated.

```bash
python3 tools/openapi_to_catalog.py openapi.json -o catalog.json \
  --base-url https://api.example.com --allow api.example.com --service example
```

## What it looks like in use

```python
h = api.get("/api/health")
print(h["status"], h["data"]["storage"])
vi.add("Service health", "health ok, storage local-json")
print(vi.stats())
```

One `run` call: an API request, a memory write and a stats read. Without memory it is just a
sandbox; the value is that the next session does not rediscover what is already known.

## What is inside

```
bin/vibocode-mcp.js        — npm entry point (starts the Python server)
vibocode/server.py         — MCP server (JSON-RPC over stdio)
vibocode/catalog.py        — catalog search, compact signatures
vibocode/aliases.json      — query alias data (natural language -> catalog terms)
vibocode/bridge.py         — bridge: ViBo memory + allowlisted HTTP
vibocode/sandbox.py        — AST validation + isolated process with limits
vibocode/runner.py         — model code executor
tools/openapi_to_catalog.py — catalog generator from OpenAPI
tests/test_mcp.py          — 19 checks
skill/                     — packaging as an agent skill (SKILL.md + CLI)
```

## Security

- imports: `json, math, re, datetime, statistics, itertools`
- forbidden: `open, eval, exec, compile, __import__, getattr, setattr`, dunder attributes,
  `global/nonlocal`, infinite loops
- network: only `api.get(path)`, only hosts from `allow_domains`
- limits: 40 s wall clock, 1.5 GB memory, 20 s CPU, output capped at 4,000 characters
- writing the same fact to memory twice is skipped

This is a Python-level sandbox (AST + rlimits + a separate process), not a V8 isolate: it
protects against accidental and careless code, not against a deliberate OS-level attack.

## Tests

```bash
python3 tests/test_mcp.py     # protocol, search, memory, API, limits, blocks
```

## Benchmarks

Tokenizer: `o200k_base` (tiktoken). Catalogs are generated from official OpenAPI specs.
"Full catalog" means one tool per endpoint, with name, description and an empty input
schema — the lower bound, generous to the alternative.

| Catalog | Actions | Full catalog | vibocode | Ratio |
|---|---|---|---|---|
| GitHub REST | 1,272 | 79,525 tokens | 217 | 366x |
| Stripe | 612 | 38,020 tokens | 217 | 175x |
| Slack Web API | 174 | 9,129 tokens | 217 | 42x |

For GitHub this is 40% of a 200,000-token window before the user says a word.

End-to-end: one `run` call with 196 tokens of code performed three requests to api.github.com,
wrote a fact to memory and read the stats back. The whole five-step exchange: 2,202 tokens.

## Search quality

Search is lexical and alias-aware. `aliases.json` maps the words a user types to catalog
terms, so a query can be phrased naturally rather than in endpoint vocabulary.

Shipped configuration (English aliases):

| Catalog | Queries | Top-1 | Top-4 |
|---|---|---|---|
| Stripe | 12 | 83% | 92% |
| GitHub REST | 5 | 40% | 80% |

With a language pack loaded through `VIBOCODE_ALIASES` (a mixed 28-query set, half of it
non-English): Stripe 80% / 95%, GitHub 38% / 75%.

Known weakness in both cases: queries that describe a whole scenario instead of an object.
Next step: hybrid BM25 + embeddings.

## Limitations

- transport is line-delimited JSON-RPC (not Content-Length); sufficient for stdio clients
- session-based endpoints need a cookie or a service token
- the catalog is static: new endpoints are added to `catalog.json` (or generated from OpenAPI)
- search is lexical, without a vector index

## License

MIT. ViBo memory is a separate product with its own license.
