# Wave 0 Embedding Spike Report
date: 2026-04-28
host: OH-Desktop
model: gemini-embedding-2

multimodal_works: true
multimodal_detail: "image=/home/sztimhdd/.hermes/omonigraph-vault/images/3738bfe579/0.jpg dim=768"
batch_api_available: false
batch_detail: "ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource has been exhausted (e.g. check quota).', 'status': 'RESOURCE_EXHAUSTED'}}"
rpm_ceiling: 100
recommendation: proceed

## Notes
- Batch API unavailable on this key. Wave 0b falls back to chunked sync embedding with per-call throttling.
