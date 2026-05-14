"""kb.services — shared service modules used by API routers.

Members (kb-3-06+):
    - search_index: FTS5 trigram helpers (SEARCH-01, SEARCH-03, DATA-07)
    - job_store: in-memory async-job dict (QA-03; reused by /api/synthesize in kb-3-08)
"""
