---
name: vibocode
description: "Use when an agent needs many API actions without flooding context: search finds the right endpoints, run executes model-written Python in a sandbox with memory and allowlisted HTTP in one call."
version: 0.1.1
tools: [python]
license: MIT
---

# ViBo Code — two tools instead of an API catalog

The problem: an API with dozens of endpoints, described as one tool per endpoint, eats the
agent's context (Cloudflare's 2,500 methods would be 1.17M tokens). The solution: two tools.

1. `search` — finds matching endpoints and memory facts for a query, returns compact
   signatures (`group_balance: GET /api/group-balance`) instead of full descriptions.
2. `run` — executes model-written Python in a sandbox: `api.get(path)` only through the
   allowlist, `vi.add/find/stats` for memory. One call closes the loop
   "found -> called -> remembered".

## When to use

- the service has dozens or hundreds of actions while the agent uses three or four;
- a chain of requests should take one call instead of ten round trips;
- the result must be written to memory so the next session does not rediscover it.

## Install

```bash
# the service action catalog
vi <package-root>/catalog.json     # base_url, allow_domains, actions[]

# start the MCP server (stdio, line-delimited JSON-RPC)
python3 <package-root>/vibocode/server.py

# PoC tests: 19 checks including sandbox blocks
python3 <package-root>/tests/test_mcp.py
```

## CLI usage

```bash
# what the service can do for this query
python3 skill/scripts/vibocode.py search "group balance"

# run code in the sandbox
python3 skill/scripts/vibocode.py run 'h = api.get("/api/health"); print(h["status"])'
```

## Security

- imports: only `json, math, re, datetime, statistics, itertools`;
- forbidden: `open, eval, exec, compile, __import__, getattr, setattr`, dunder attributes,
  `global/nonlocal`, infinite loops;
- network: only `api.get(path)`, only domains from `allow_domains`;
- limits: 40 s per run, 1.5 GB memory, 20 s CPU, output capped at 4,000 characters;
- writing the same fact twice is skipped (duplicate protection).

## Limitations

- a Python-level sandbox (AST + rlimits + a separate process), not a V8 isolate;
- session-based methods need a cookie or a service token;
- the catalog is static: a new endpoint is added to `catalog.json`.

## Quality check

Clone the ViBo-SkillQA repository and run this skill directory through its checker:

```bash
git clone https://github.com/vnbochkarev-netizen/ViBo-SkillQA.git
cd ViBo-SkillQA && python3 <checker-script> test <path-to-this-directory> --lang en
```
