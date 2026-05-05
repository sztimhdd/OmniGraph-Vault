# LightRAG 1.4.15 Internals → Scaling Hypothesis Verdicts

**Date:** 2026-05-04
**Quick task:** 260504-x3s
**LightRAG version:** 1.4.15 (`venv/Lib/site-packages/lightrag/_version.py`)
**Mode:** Read-only research; no source-code edits anywhere.

All citations refer to the venv-installed copy:
`venv/Lib/site-packages/lightrag/...` (and `nano_vectordb/...`).

---

## Executive Summary

| ID | Hypothesis | Verdict |
|----|------------|---------|
| **S** | Serial embed loop matters because LightRAG passes 1-text batches | **CONFIRMED for entities/relations; REFUTED for chunks** — entity/relation vdb upserts pass single-item dicts, so `embedding_func(["one text"])` is the steady-state shape; chunks_vdb does pass real batches of `embedding_batch_num` (default 10). |
| **A** | nano-vectordb upsert is full-file JSON rewrite | **CONFIRMED** — `NanoVectorDB.save()` serializes the entire `__storage` dict + base64-encoded matrix to one JSON file in a single `json.dump` call. |
| **B** | networkx graphml save is full XML serialization, triggered per ainsert | **CONFIRMED** — `nx.write_graphml()` (full XML) runs inside `index_done_callback`, which `ainsert()` invokes once **per file processed**. |
| **C** | `FORCE_LLM_SUMMARY_ON_MERGE=8` triggers more often as N grows | **CONFIRMED** — trigger is `len(description_list) >= 8 OR total_tokens >= 1200`; `description_list = already_description + new`, which grows with every revisit of an entity. |

---

## Hypothesis S — Serial embed loop & shape of `embedding_func` calls

**Status:** CONFIRMED for entity/relation paths · REFUTED for chunk path

**Evidence:**

- `venv/Lib/site-packages/lightrag/operate.py:1920-1938` — entity merge upsert is a single-item dict:
  ```python
  if entity_vdb is not None:
      entity_vdb_id = compute_mdhash_id(str(entity_name), prefix="ent-")
      entity_content = f"{entity_name}\n{description}"
      data_for_vdb = {
          entity_vdb_id: { "entity_name": entity_name, ... "content": entity_content, ... }
      }
      await safe_vdb_operation_with_exception(
          operation=lambda payload=data_for_vdb: entity_vdb.upsert(payload), ...)
  ```

- `venv/Lib/site-packages/lightrag/operate.py:2472-2490` — relation upsert: same shape, one `{rel_vdb_id: {...}}` per call. Three other entity-vdb upsert sites (`:1147`, `:2291`, `:2410`) all pass single-item dicts.

- `venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py:108-124` — the storage upsert chops the incoming dict by `embedding_batch_num`, then calls `embedding_func` once per batch via `asyncio.gather`:
  ```python
  list_data = [ {"__id__": k, ..., **v} for k, v in data.items() ]
  contents = [v["content"] for v in data.values()]
  batches = [contents[i : i + self._max_batch_size]
             for i in range(0, len(contents), self._max_batch_size)]
  embedding_tasks = [self.embedding_func(batch) for batch in batches]
  embeddings_list = await asyncio.gather(*embedding_tasks)
  ```
  When `data` has 1 entry, `batches = [["one text"]]` → exactly one `embedding_func(["one text"])` call.

- `venv/Lib/site-packages/lightrag/lightrag.py:1311-1338` — chunks path is different: `inserting_chunks` is built as a **multi-chunk dict** before `self.chunks_vdb.upsert(inserting_chunks)`, so `batches` is `ceil(N_chunks / 10)` real batches of size 10.

**Mechanism (≤3 sentences):**
LightRAG's entity/relation merge layer (`_merge_nodes_then_upsert`, `_merge_edges_then_upsert`) calls `entities_vdb.upsert({single_id: {...}})` once per entity/edge inside a `Semaphore(graph_max_async)` (default `llm_model_max_async * 2 = 8`). Each of those single-item upserts triggers exactly one `embedding_func(["one text"])` call inside `nano_vector_db_impl.upsert`. Only `chunks_vdb` receives a multi-key dict and therefore actually exercises the `embedding_batch_num` batching path.

**Scaling implication:**
On a per-article basis: `embed_api_calls ≈ N_chunks/10 (chunks) + N_entities (entities) + N_edges (edges)`. Entities + edges dominate at large `N` (Hermes: ~90 entities + ~150 edges/article ≫ ~8 chunks/article). So even if `lib/lightrag_embedding.py:207` (the host-side `for text in texts` loop) is rewritten to call Vertex's batch API, the **upstream caller** still passes a 1-item list per entity/edge. The remaining win is the in-flight concurrency from `embedding_func_max_async` × `Semaphore(graph_max_async)` — **not** larger HTTP batches.

**Recommendation for benchmark spec / fix:**
Keep S0/S1/S2 in the spec, but adjust S2's promised win. The realistic cap is "1 RTT × graph_max_async × embedding_func_max_async in flight" (~16-32 concurrent 1-text calls), **not** "20 texts in one call." A single-call N-text Vertex batch would require also collapsing the per-entity upsert sites in `operate.py` to bulk upserts — that is **out of scope** for the host-side fix at `lib/lightrag_embedding.py`. State 2's prediction in §3 ("another 10–20× faster on the embed stage") is optimistic; expect closer to 3–6× from concurrency alone.

---

## Hypothesis A — nano-vectordb full JSON rewrite per upsert

**Status:** CONFIRMED

**Evidence:**

- `venv/Lib/site-packages/nano_vectordb/dbs.py:137-143` — `save()` is a single full-file `json.dump`:
  ```python
  def save(self):
      storage = {
          **self.__storage,
          "matrix": array_to_buffer_string(self.__storage["matrix"]),
      }
      with open(self.storage_file, "w", encoding="utf-8") as f:
          json.dump(storage, f, ensure_ascii=False)
  ```
  The matrix is base64-encoded (`array_to_buffer_string`, `:27-28`) into one giant string. No appending, no incremental writer.

- `venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py:273-304` — `index_done_callback` is the only place `_client.save()` is called (other than `drop()` for a wipe):
  ```python
  async def index_done_callback(self) -> bool:
      ...
      async with self._storage_lock:
          ...
          self._client.save()
  ```

- `venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py:96-137` — `upsert()` only mutates `self.__storage["matrix"]` and `self.__storage["data"]` in memory; nothing touches disk.

**Mechanism (≤3 sentences):**
`NanoVectorDBStorage.upsert()` is in-memory only; the actual disk persistence is deferred to `index_done_callback()`, which calls `client.save()` and rewrites the entire `vdb_*.json` file (id list + base64-encoded float32 matrix) in one `json.dump` write. Three vdb files exist: `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` — each is rewritten in full on every `index_done_callback`.

**Scaling implication:**
Per `index_done_callback` call: **O(N_total_rows × embedding_dim)** bytes written. At Hermes-scale (~26-30 MB `vdb_*.json` files), that's a 26+ MB write per file per article. The cost of `save()` is independent of how many rows changed — adding 1 entity rewrites the whole file.

**Recommendation for benchmark spec / fix:**
Keep §5 row for A. Concretely measurable via `vdb_upsert_sec` + the proxy metric `vdb_entities_bytes_after`. The §5 fingerprint ("`vdb_upsert_sec` >30% of total + grows linearly with bytes") is already calibrated correctly; the **growth driver is total file size, not delta size**. Expect linear-in-N share growth without any threshold.

---

## Hypothesis B — networkx graphml full XML serialization, triggered per ainsert

**Status:** CONFIRMED

**Evidence:**

- `venv/Lib/site-packages/lightrag/kg/networkx_impl.py:33-38` — write helper is plain `nx.write_graphml`:
  ```python
  @staticmethod
  def write_nx_graph(graph: nx.Graph, file_name, workspace="_"):
      logger.info(
          f"[{workspace}] Writing graph with {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
      )
      nx.write_graphml(graph, file_name)
  ```
  GraphML is an XML format — it has no append semantics. Each call serializes the entire graph from scratch.

- `venv/Lib/site-packages/lightrag/kg/networkx_impl.py:540-571` — `index_done_callback()` is the only writer, and it always calls `write_nx_graph(self._graph, ...)` on the full graph object.

- `venv/Lib/site-packages/lightrag/lightrag.py:2339-2360` — `_insert_done()` fires `index_done_callback()` on every storage in parallel:
  ```python
  async def _insert_done(self, ...):
      tasks = [
          cast(StorageNameSpace, storage_inst).index_done_callback()
          for storage_inst in [
              self.full_docs, self.doc_status, self.text_chunks,
              self.full_entities, self.full_relations,
              self.entity_chunks, self.relation_chunks,
              self.llm_response_cache,
              self.entities_vdb, self.relationships_vdb, self.chunks_vdb,
              self.chunk_entity_relation_graph,
          ]
          ...
      ]
      await asyncio.gather(*tasks)
  ```

- `venv/Lib/site-packages/lightrag/lightrag.py:2180-2181` — `_insert_done` runs **after each file** processed in the pipeline:
  ```python
  # Call _insert_done after processing each file
  await self._insert_done()
  ```

**Mechanism (≤3 sentences):**
On every `ainsert()` of a single doc, after extract+merge complete, `_insert_done()` calls `index_done_callback()` on every storage in parallel; for the NetworkX graph that means `nx.write_graphml(self._graph, …)` — full XML re-serialization of every node and edge. Trigger frequency is **once per document insertion**, not batched across multiple documents. Both A (`vdb_*.json`) and B (`graph_*.graphml`) are rewritten in the same `_insert_done()` burst.

**Scaling implication:**
Per article: **O(N_nodes + N_edges)** XML serialization + disk write. At Hermes ~1500 nodes, graphml is plausibly 1-3 MB (rough estimate: ~700 bytes XML/node from `entity_id`/`description`/`source_id`/`file_path` attrs which can each be 100-500 chars; per-edge similar). XML serialization itself is CPU-bound at this scale — likely sub-second per article — but it grows linearly with N and runs **on every ainsert**, not just at end-of-batch.

**Recommendation for benchmark spec / fix:**
Keep `graphml_save_sec` as a per-article metric in §4. The §5 fingerprint ("`graphml_save_sec >20%` of total at large N") is plausible only if the file gets very large or the network FS is slow. On a local SSD, expect this to remain a few percent — **B is real but probably not the dominant driver**. Still worth measuring: if it ever crosses ~10% at N=1000, that's actionable signal for swapping to Neo4j/Postgres backend.

---

## Hypothesis C — `FORCE_LLM_SUMMARY_ON_MERGE=8` trigger condition & growth with N

**Status:** CONFIRMED

**Evidence:**

- `venv/Lib/site-packages/lightrag/constants.py:19` — default is 8:
  ```python
  DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE = 8
  ```
  (NOT 1 as some Hermes notes claimed.)

- `venv/Lib/site-packages/lightrag/operate.py:205-227` — exact trigger condition:
  ```python
  force_llm_summary_on_merge = global_config["force_llm_summary_on_merge"]
  ...
  while True:
      total_tokens = 0
      for i, desc in enumerate(current_list, start=1):
          total_tokens += len(tokenizer.encode(desc))
          ...
      if total_tokens <= summary_context_size or len(current_list) <= 2:
          if (
              len(current_list) < force_llm_summary_on_merge
              and total_tokens < summary_max_tokens
          ):
              # no LLM needed, just join the descriptions
              final_description = separator.join(current_list)
              return final_description if final_description else "", llm_was_used
          else:
              # Final summarization of remaining descriptions - LLM will be used
              final_summary = await _summarize_descriptions(...)
              return final_summary, True
  ```
  LLM summary fires when **EITHER** `len(description_list) >= 8` **OR** `total_tokens >= summary_max_tokens (default 1200, `constants.py:21`)`.

- `venv/Lib/site-packages/lightrag/operate.py:1782` — `description_list` is the cumulative list:
  ```python
  # Combine already_description with sorted new sorted descriptions
  description_list = already_description + sorted_descriptions
  ```
  Where `already_description` is split from the existing graph node's `description` field (`:1670-1672`) — i.e. every prior merge adds to it.

**Mechanism (≤3 sentences):**
For each entity/relation merge, LightRAG concatenates already-stored descriptions (from past merges) with newly extracted ones. If the combined list has ≥8 items **or** exceeds 1200 tokens, a per-entity LLM summary call fires. Popular entities (e.g. "OpenAI", "LightRAG", "Agent") accumulate description fragments fastest as more articles mention them, so they cross the threshold earliest.

**Scaling implication:**
`llm_merge_summary_count` per article is **NOT constant**. Heavy-tail entities (the 10-20% that get re-mentioned) cross the 8-fragment threshold mid-corpus and then trigger a summary on **every** subsequent merge (because the summary writes back as 1 description but the next article adds 1+ more, immediately re-tripping the threshold once `total_tokens > 1200`). Effective scaling is **super-linear in cumulative entity-revisits**, not in N alone — the tail of high-degree entities drives the growth.

**Recommendation for benchmark spec / fix:**
Keep §5 row for C. The fingerprint should be sharpened: instead of "`llm_merge_summary_count` per article grows with N," measure per-article **`llm_merge_summary_count / new_entities_this_article`** — a constant ratio refutes C; a rising ratio confirms it. Hot-entity churn is the real metric.

---

## Secondary Questions

### Q1. Batch path through LightRAG — does it pass real `List[str]` batches?

**Answer (split): YES for chunks_vdb, NO for entities_vdb / relationships_vdb.**

- Chunks: `lightrag.py:1311-1338` builds a multi-chunk dict and passes it to `chunks_vdb.upsert(inserting_chunks)`. Inside `nano_vector_db_impl.py:117-120`, the dict is re-batched by `embedding_batch_num=10`. Real batches of 10 hit `embedding_func`.
- Entities: `operate.py:1923-1938` passes a 1-item dict per entity, fanned out via `Semaphore(graph_max_async)` (default 8). Each call is `embedding_func(["one text"])`.
- Relations: `operate.py:2472-2485` — same shape as entities, 1-item dict.

**Implication for `lib/lightrag_embedding.py:207` fix:** rewriting the host-side `for text in texts` loop into a Vertex batch API call only helps the chunks path (and only marginally — there are ~5-30 chunks/article at Hermes config, vs hundreds of entities + edges). To get a real batch-API win on entities/edges, LightRAG itself would need bulk upsert paths — that is upstream work, not a host-side fix.

### Q2. Graphml file size at N=1533 + disk-write time

**Estimate: 1.5–4.5 MB; write time ~0.3–1.5 s on local SSD.**

NetworkX graphml writes per-node/per-edge XML elements. Each LightRAG node carries attributes:
`entity_id`, `entity_type`, `description` (often 200-1500 chars after summary), `source_id` (chunk-id list, can be 200+ chars at high source_id limits), `file_path` (similar), `created_at`, `truncate`. Conservative per-node XML ~700 bytes; per-edge similar.

For `N=1533` nodes and assuming ~1.5× edges (Hermes shape): `1533 × 700 + ~2300 × 700 ≈ 2.7 MB`. Range 1.5-4.5 MB depending on description length spread. `nx.write_graphml` walks node+edge dicts in one pass, so XML serialization is O(N+E) plus the OS-level write. On a local SSD that's well under a second; on a network mount it can hit seconds.

This is large enough to **see** but not large enough to dominate at N=1500. The bigger question is whether the **per-article cumulative** time becomes meaningful: 20 articles × 1 s/article = 20 s of total ingest budget burned on graphml — visible but not catastrophic. Becomes catastrophic only at N=10,000+.

---

## Implications for Benchmark Spec (`docs/lightrag_scaling_benchmark_spec.md` §5)

**Keep (no change):**
- **A row** — fingerprint as written ("`vdb_upsert_sec` > 30%, grows linearly with `vdb_entities_bytes_after`") matches code exactly.
- **B row** — measurement instrumentation correct; the >20% threshold is appropriate for "structural problem" vs "real but minor."
- **D2 stacked-area chart** — still the right visualization.

**Refine (small wording / threshold edits):**
- **S row** — adjust prediction. The §3 prediction "S1 → S2: another 10-20× faster on the embed stage" is too optimistic. The S2 win comes from in-flight concurrency, not from collapsing N-text calls into 1 batch (because LightRAG passes 1-item dicts on the entity/relation path). Realistic S2 vs S1 multiplier is **3-6×** on the embed stage from concurrency, not 10-20×.
- **C row** — sharpen fingerprint. "`llm_merge_summary_count` per article grows with N" is too coarse; replace with "**`llm_merge_summary_count / new_entities_per_article` rises with cumulative N**" — i.e. measure rate of summary trigger per *new* entity, not absolute count. Add `total_tokens` check: track whether the 1200-token branch (not the 8-fragment branch) is the actual trigger.

**Drop (none).** All four hypotheses have non-negligible code-path support; none should be removed.

**Add (one):**
- A **5th metric** — `entity_merge_revisit_ratio` = `(merged_existing_entities) / (new + merged_entities)` per article. This is the upstream cause of C. If revisit_ratio rises with N (heavy-tail revisit dominates), that's the real driver — not the threshold, but the input distribution.

---

*End of research doc — 2026-05-04, Quick 260504-x3s.*
