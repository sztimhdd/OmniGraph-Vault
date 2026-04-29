# Plan 05-00c Smoke Test Log

date: 2026-04-28
executor: Plan 05-00c Task 0c.6
script: scripts/wave0c_smoke.py
run_host: remote WSL (OH-Desktop)
working_dir: /tmp/wave0c_smoke_cs39pkvk (private temp — production graph untouched)

## Inputs

doc_id: doc-886de7530a4df0deef83664ecf21c252
doc_size_chars: 4539
doc_truncated_to: 4000 chars (first N chars for smoke bounds)
key_pool_size: 2
llm_provider: deepseek (deepseek-v4-flash)
embedding_provider: gemini (gemini-embedding-2)

## Outputs

embed_calls: 45 (22 entities + 22 relations + 1 chunk, single LightRAG batch)
llm_calls: ≥2 (entity extraction + relationship extraction — exact count
  not instrumented; visible as "LLM cache saving" lines in LightRAG log)
deepseek_invoked: true
gemini_llm_invoked: false
key_rotation_hits: {AIzaSy...fc_g7g: 45, AIzaSy...GzBJQ8: 0}
final_vdb_embedding_dim: 3072
result: pass

## Evidence

- LightRAG log shows: "Chunk 1 of 1 extracted 22 Ent + 22 Rel chunk-4893..." — entities
  were successfully extracted via the Deepseek wrapper (would have 429'd or
  failed to parse if Gemini LLM had been involved — Gemini's free-tier
  generate_content quota was drained earlier in the day).
- LightRAG log: "Init {'embedding_dim': 3072, 'metric': 'cosine', ...}" for all three
  vdb_*.json files (entities, relationships, chunks) — confirms the wipe-and-rebuild
  path preserves the Phase 7 D-10 3072-dim contract.
- LightRAG log: "Writing graph with 22 nodes, 22 edges" + "Completed merging: 22
  entities, 22 relations" — end-to-end ingest succeeded.
- Deepseek endpoint: api.deepseek.com/v1/chat/completions (via
  openai.AsyncOpenAI base_url in lib/llm_deepseek.py).

## Observations

1. **All 45 embed calls landed on key A (the primary).** Key B was in the
   pool (key_pool_size=2) but never exercised. This is expected and healthy
   — the primary key had refreshed quota earlier in the day, so no 429s
   triggered failover. Rotation behavior under load will be visible when
   (a) primary hits 429 mid-run, or (b) we apply a forced round-robin.
   Unit tests prove rotation correctness across both axes
   (test_round_robin_two_keys + test_429_failover_within_single_call).

2. **Key rotation telemetry is fit-for-purpose.** The smoke confirmed:
   - Pool has 2 keys.
   - _ROTATION_HITS counter tracks successful calls per key.
   - Production graph unaffected (smoke used a private temp working dir).

3. **Gemini generate_content quota confirmed decoupled from the pipeline.**
   This doc was ingested during the 15-min window after
   scripts/wave0_reembed.py's 5th attempt 429'd on the primary — the fact
   that this smoke PASSED (instead of 429'ing on entity extraction) proves
   that LightRAG's LLM path is now fully on Deepseek.

## Hand-off

The Wave 0 runtime (Plan 05-00) should now retry successfully:

```
ssh -p 49221 sztimhdd@ohca.ddns.net \
  "cd ~/OmniGraph-Vault && source venv/bin/activate && \
   python scripts/wave0_reembed.py --i-understand"
```

Expected: ~1200 embed calls spread across 2 keys (primary + backup),
0 `generativelanguage.googleapis.com/...generate_content` calls (all LLM now
goes to api.deepseek.com). If quota hits are still reached, rotation will
transparently failover within each call until both keys are 429 (then the
plan-level guard RuntimeError surfaces).
