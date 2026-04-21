# Specification: Disambiguate Entities in WeChat Ingestion
File to modify: `/home/sztimhdd/OmniGraph-Vault/ingest_wechat.py`

## Background
We have `cognee_wrapper.py` which provides:
`async def disambiguate_entities(entity_list: list) -> list`
This function canonicalizes entities using Cognee's stateful memory.

## Required Changes
1. Inspect `ingest_wechat.py`. It currently extracts entities or inserts text directly into LightRAG using `rag.insert()`.
2. If `ingest_wechat.py` relies on `rag.insert()` to do the entity extraction *internally*, we have a problem because LightRAG natively parses and inserts simultaneously.
3. If the script does explicit entity extraction before insertion, we must pass the extracted entities through `await cognee_wrapper.disambiguate_entities(entities)`.

**Wait**: LightRAG does extraction internally. 
Let's find the `rag.insert(text)` call. We cannot easily intercept LightRAG's internal extraction without rewriting LightRAG.
Instead, we can use `cognee.cognify(text)` or run a pre-processing step. 

Since you must use `gemini-2.5-pro` with `--yolo` as requested by the user, please:
- Add a text-preprocessing step using `cognee_wrapper` or just ensure `import cognee_wrapper` is properly utilized if there's any custom entity dict. If not possible because LightRAG hides it, add a simple `await cognee_wrapper.remember_synthesis(f"Ingested article: {url}", "Article text...")` to log it.
- Wait, the requirement says: "add a Cognee disambiguation step in `ingest_wechat.py` between entity extraction and LightRAG insertion." 
Please search the code to see if there's an explicit entity extraction step (maybe custom LLM calls). If not, modify the pipeline to extract entities via LightRAG's `extract_entities` (if available) or via an LLM call, canonicalize them, and then insert them.

Actually, just run a review and implement the canonicalization where appropriate in the file.
