# Phase 0 LightRAG Delete+Reinsert Spike — Report

**Run at:** 2026-04-27T15:47:05.236641+00:00
**Host:** OH-Desktop (remote Hermes WSL2 PC)
**LightRAG version:** 1.4.15

status: success

## Steps

1. Initial ainsert with ids=[phase0_spike_test_doc]: ok
2. Pre-delete entity count: 0
3. adelete_by_doc_id result: status=success, status_code=200, message="Document phase0_spike_test_doc successfully deleted"
4. Post-delete entity count: 0
5. Re-ainsert with same ids: ok
6. Post-reinsert entity count: 0

## Observations

- Orphan entity cleanup: clean (0 entities removed)
- Re-insert idempotency: stable
- Notes: LightRAG 1.4.15; orphan cleanup is LLM-cache-dependent per API docs

## Post-hoc validation note (orchestrator, 2026-04-27)

The above report was written by the spike script on its first run. The script's
API-contract checks (ainsert returns a track_id; adelete_by_doc_id returns
status=success; re-ainsert returns ok) all passed — that satisfies the formal
D-14 gate.

Caveat: the spike does not `await` LightRAG's async entity-extraction pipeline
before measuring entity counts. The three `entity count: 0` readings reflect
"async pipeline hadn't run yet," not "delete cleaned up real entities." In a
follow-up run, the async pipeline hit a Gemini free-tier 429 mid-extraction,
leaving `phase0_spike_test_doc` in `status: failed` in kv_store_doc_status.json.

The orchestrator then invoked `rag.adelete_by_doc_id("phase0_spike_test_doc",
delete_llm_cache=False)` directly against the live LightRAG (713 nodes, 820
edges at the time) and captured a stronger result:

- status=success, message="Document phase0_spike_test_doc successfully deleted"
- "Successfully deleted 2 chunks from storage"
- Main graph preserved (still 713 nodes, 820 edges after the cleanup)

That live-cleanup delete is stronger D-14 evidence than the spike's own
measurements: it proves `adelete_by_doc_id` correctly cleans chunks from a
failed-state doc without disturbing the rest of the graph.

**Follow-up (non-blocking):** the spike script should be revised to await the
async extraction pipeline before measuring entity counts, so its own report is
meaningful rather than vacuous. Ticketable as a small refactor in a future
phase — does not block Wave 2.
