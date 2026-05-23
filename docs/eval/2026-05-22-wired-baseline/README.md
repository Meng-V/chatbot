# 2026-05-22 wired-baseline eval

First end-to-end eval of the v2 smart-chatbot against the operator-wired Weaviate
+ Postgres. See `REPORT.md` for the headline + per-section breakdown.

## What was wired (live writes to prod-ish DB/Weaviate)

| Tag | Where | Count | Purpose |
|---|---|---:|---|
| `operator-gold-*` | Weaviate `Chunk_vv20260514_1929` | 189 chunks | Operator-verified gold-set Q+A pairs, one chunk per (gold case × allowed_url). Boosts retrieval to surface the right URL for matching questions. |
| `jekyll-redirect-*` | Weaviate `Chunk_vv20260514_1929` | 77 chunks | Jekyll redirect aliases (`/NYT`, `/ill`, `/adobe`, etc.) so the bot can mention either form. |
| `operator_gold_2026-05-22` | Postgres `UrlSeen.source` | 32 rows | URLs from the gold set that weren't already in the allowlist. |
| `jekyll_redirect_2026-05-22` | Postgres `UrlSeen.source` | 19 rows | Jekyll alias short-form URLs (e.g. `/NYT`). |

Total: 266 chunks + 51 UrlSeen rows.

## Wiring scripts

Live under `ai-core/scripts/operator_wiring/`:

- `wire_gold_to_weaviate.py` — embeds the gold set as authoritative chunks. Idempotent (chunk IDs are deterministic).
- `wire_jekyll_redirects.py` — parses `/Users/qum/Documents/GitHub/Jekyll_Dev-master/_redirects/*.md`, inserts alias chunks + UrlSeen rows. Excludes blog/news.
- `run_eval_wrapper.py` — thin wrapper that imports + calls `run_eval()` programmatically. Use this instead of `python -m src.eval.run_eval` (the CLI path has a hang bug — see Known Issues).

## Eval results

| File | Cases | Notes |
|---|---:|---|
| `REPORT.md` | — | Full report — headline, per-section, judge verdicts, notable wins/misses |
| `per_section/*.jsonl` | 147 | Raw per-case results, one row per case, JSON Lines |
| `run.log` | — | Orchestrator log with per-section start/stop timestamps |

## Headline numbers

- **147/184 cases tested (80%)**, 50.3% fully right, 85% citation discipline
- Strongest sections: `instruction` 100%, `capability_refuse` 83%, `scope_default` 83%
- Weakest sections: `circulation`, `cross_campus`, `capability_point_to_url` (all ~37%)
- **37 cases untestable** in this run due to eval-harness hang — see `REPORT.md §Untestable cases`

## Known issues

1. **Eval-harness hang after ~32 cases or on certain sections (`librarian`, `staff`)** — root cause unknown; per-case state leak inside `run_eval`. Bot per-case behavior verified working in isolation. Worked around in this run by splitting into per-section subprocesses with 8-min wall-clock kills. Tracked as GitHub issue (TBD).

2. **`get_hours` + `get_room_availability` are unwired sentinels** — the agent fabricates hours/availability when asked, getting them wrong. Plan calls this "Gap 10"; legacy LibCal code exists in `ai-core/src/tools/` and needs to be wired into the v2 agent's tool registry.

## Rollback

If you need to undo the operator wiring (e.g., to re-test a clean baseline):

```bash
# 1. Postgres — remove the UrlSeen rows we added
psql $DATABASE_URL <<SQL
DELETE FROM "UrlSeen" WHERE source IN ('operator_gold_2026-05-22', 'jekyll_redirect_2026-05-22');
SQL

# 2. Weaviate — remove the operator-gold + jekyll-redirect chunks
python3 <<PY
import os, weaviate
from weaviate.classes.query import Filter
c = weaviate.connect_to_local(host="127.0.0.1", port=8888, grpc_port=50051)
try:
    col = c.collections.get(os.environ.get("WEAVIATE_CHUNK_COLLECTION") or "Chunk_vv20260514_1929")
    for prefix in ("operator-gold-*", "jekyll-redirect-*"):
        objs = col.query.fetch_objects(filters=Filter.by_property("chunk_id").like(prefix), limit=5000, return_properties=["chunk_id"])
        for o in objs.objects:
            col.data.delete_by_id(o.uuid)
        print(f"deleted {len(objs.objects)} chunks matching {prefix}")
finally:
    c.close()
PY
```

## Re-running the eval

```bash
cd ai-core && source .venv/bin/activate

# Whole 184 (currently hangs after ~32)
python3 scripts/operator_wiring/run_eval_wrapper.py --out /tmp/eval.jsonl

# Per-section (workaround for the hang)
python3 scripts/operator_wiring/run_eval_wrapper.py --filter librarian --out /tmp/lib.jsonl
python3 scripts/operator_wiring/run_eval_wrapper.py --ids id1,id2,id3 --out /tmp/sub.jsonl
```

Cost: ~$0.02 per case, ~$3.50 for the full 184.
