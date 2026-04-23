---
type: quick
quick_id: 260422-jej
autonomous: true

must_haves:
  truths:
    - "Python venv created with all deps installed (lightrag, cognee, google-generativeai)"
    - "3 WeChat articles ingested without crash or path errors"
    - "Entity buffer populated with _entities.json files for each article"
    - "canonical_map.json created by cognee_batch_processor.py"
    - "Cross-article synthesis references entities from >= 2 articles"
    - "Images downloaded and described by Gemini Vision"
    - "Intermediate outputs logged at each pipeline stage for quality review"
---

<objective>
Set up local Python venv, install all dependencies, and run the full OmniGraph-Vault
pipeline end-to-end with 3 real WeChat articles. Log all intermediate data at each stage
so the user and Claude can evaluate data quality — not just "did it crash?"

Test URLs:
- https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA
- https://mp.weixin.qq.com/s/8SGRMIyspvUcLMcmeDa2Mw
- https://mp.weixin.qq.com/s/4bE4AZPAAYVdtQIlf9hP9A
</objective>

<tasks>

<task type="auto">
  <name>Task 1: Setup venv and install dependencies</name>
  <action>
    Create Python venv, install requirements.txt, verify key imports (lightrag, cognee, google-generativeai).
    Create runtime data directory if missing.
  </action>
  <verify>
    python -c "import lightrag; import cognee; print('OK')"
  </verify>
</task>

<task type="auto">
  <name>Task 2: Ingest 3 WeChat articles with verbose logging</name>
  <action>
    For each of the 3 test URLs, run ingest_wechat.py and capture:
    - Scraping method used (Apify vs CDP vs MCP)
    - Article title extracted
    - Markdown content length (chars and words)
    - Number of images found, downloaded, and described
    - Entity extraction results (entity names and types)
    - LightRAG insertion confirmation
    - Entity buffer file created

    After all 3, inspect:
    - ~/.hermes/omonigraph-vault/entity_buffer/ — list all files
    - ~/.hermes/omonigraph-vault/images/ — list directories and image counts
    - ~/.hermes/omonigraph-vault/lightrag_storage/ — confirm KG data exists
  </action>
  <verify>
    3 entity buffer files exist, 3 image directories exist, lightrag_storage populated
  </verify>
</task>

<task type="auto">
  <name>Task 3: Run batch processor and validate canonical_map.json</name>
  <action>
    Run cognee_batch_processor.py, then inspect:
    - canonical_map.json contents (entity mappings, aliases)
    - Number of canonical entities discovered
    - Quality check: do mappings make sense for the ingested content?
  </action>
  <verify>
    canonical_map.json exists, is valid JSON, contains entity mappings
  </verify>
</task>

<task type="auto">
  <name>Task 4: Run cross-article synthesis and evaluate quality</name>
  <action>
    Run kg_synthesize.py with a cross-article query. Capture:
    - Full synthesis output
    - Word count
    - Which articles/entities are referenced
    - Whether image references appear in output
    - synthesis_output.md file content

    Also run a second query targeting image-based content specifically.
  </action>
  <verify>
    Synthesis references entities from >= 2 articles, output >= 200 words
  </verify>
</task>

</tasks>
