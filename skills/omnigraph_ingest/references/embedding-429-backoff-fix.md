# Embedding 429 — Vertex AI Diagnosis & Three-Layer Fix

**Filed:** 2026-07-20 (v1/v2), 2026-07-20 (v3 batch)
**Severity:** High — caused 54 service restart loops on Aliyun (2026-07-16)
**Root cause:** Vertex AI embedding RPM/RPD quota too low (50 RPM max) for batch ingest load.
**Fix:** Batch embedding (Layer 1, primary) + exponential backoff (Layer 2, fallback).

## Evolution

| Version | Approach | Throughput @50 RPM |
|---------|----------|--------------------|
| v1 | Fixed 300s cooldown on 429 | <50 texts/min → death spiral |
| v2 | Pre-call 1.2s rate limiter + exponential backoff | ~50 texts/min |
| v3 | **Batch 250 texts per API call** | **12,500 texts/min** |

## Diagnostic Playbook

Run IN ORDER:

### 1. Rapid Quota Test (measure actual RPM)
```bash
source /root/.hermes/.env && cd /root/OmniGraph-Vault && venv-aim1/bin/python -c "
import asyncio; from google import genai; from google.genai import types
client = genai.Client(vertexai=True, project='banded-totality-485901', location='global')
async def t():
    for i in range(30):
        try:
            r = await client.aio.models.embed_content(
                model='gemini-embedding-2', contents=['q'+str(i)],
                config=types.EmbedContentConfig(output_dimensionality=3072))
            print('OK', i, end=' ')
        except Exception as e:
            msg = str(e)[:80]
            print('\n429 at', i, ':', msg); break
asyncio.run(t())
"
```
- Aliyun SA: typically 20+ OK before throttle (good).
- WSL SA: 7 OK (lower — SA on WSL has different quota pool).

### 2. Check 429 Pattern in Journal
```bash
journalctl -u omnigraph-daily-ingest --no-pager -S "2 days ago" | grep "burst\|cooldown"
```
Post-fix (v2), look for:
- `burst #1, cooldown 34s` — first 429, 30s base + jitter
- `burst #2, cooldown 69s` — second consecutive, doubled
- If bursts reset to #1 after success: backoff is recovering normally

Pre-fix (v1), look for:
- Fixed 300s intervals: `22:30→22:35→22:40→22:45…` → service timeout death spiral

### 3. Service Restart Counter
```bash
systemctl show omnigraph-daily-ingest -p NRestarts
```
>50 → aggressive restart storm (pre-fix). Post-fix should be 0 for days.

## What Changed (v3, 2026-07-20 — Batch Embedding)

### Layer 1: Batch embedding (primary — replaces v2 rate limiter)

The key insight: 50 RPM limits **requests**, not texts. Gemini's `embed_content` accepts
up to 250 texts per call. Batching 250 texts/request at 50 RPM = 12,500 texts/min.

In `lib/lightrag_embedding.py`:

```python
_MAX_BATCH_SIZE = 250  # max texts per single embed_content call
```

**`_embed_once`** — now returns ALL embeddings from a batch call:
```python
vecs = np.array([e.values for e in response.embeddings], dtype=np.float32)
return vecs  # shape (N, 3072), was (1, 3072)
```

**`_embed`** — separates pure-text from multimodal chunks:
- Pure text (no image URLs) → batched in groups of 250 → one API call per batch
- Multimodal (contains `http://localhost:8765/...png|jpg`) → individual calls
  (each requires its own `types.Part` payload)
- Results interleaved back in original order → L2 normalize

**Removed:** `_VERTEX_MIN_GAP_S` (1.2s gap), `_LAST_EMBED_CALL_TS` — no longer needed.

**Smoke tests:**
- 5 pure-text → 1 API call (was 5)
- 300 pure-text → 2 API calls (250 + 50, was 300)
- 2 pure + 1 multimodal → 2 API calls (1 batch + 1 individual, was 3)

### Layer 2: Exponential backoff (unchanged from v2)

```python
_COOLDOWN_BASE = 30            # seconds
_COOLDOWN_MAX = 1800           # 30 min cap
_CONSECUTIVE_429_BURSTS = 0    # global counter, reset on success

# Cooldown = min(30 * 2^(bursts-1), 1800) * (1 ± 25% jitter)
delay = min(_COOLDOWN_BASE * (2 ** (_CONSECUTIVE_429_BURSTS - 1)), _COOLDOWN_MAX)
jitter = delay * 0.25 * (2 * random() - 1)
cooldown = delay + jitter
```

**Behavior:**
| Burst # | Base Delay | Jitter Range | Total |
|---------|-----------|-------------|-------|
| 1       | 30s       | ±7.5s       | 22-38s |
| 2       | 60s       | ±15s        | 45-75s |
| 3       | 120s      | ±30s        | 90-150s |
| 6+      | 960s→1800s| ±240-450s   | 720-2250s |

### Error Messages (post-fix)
```
Vertex AI embedding quota 429 — RPM/RPD exceeded (burst #3, cooldown 142s).
Check GCP quota dashboard for aiplatform.googleapis.com or reduce embedding concurrency.
```

## Quota Reality

The paid-tier Vertex AI `gemini-embedding-2` quota is capped at **50 RPM**:
- GCP Console → IAM → Quotas → `aiplatform.googleapis.com` → "Online prediction requests per minute"
- Max value: 50 (cannot increase — "not eligible for a quota increase at this time")
- This is a HARD ceiling, not a configuration oversight
- Design rate limiters around 50 RPM, not "unlimited paid tier"

## Auth Investigation (2026-07-20, 2h)

ADC (`authorized_user` with `gcloud auth application-default login`) was attempted as an alternative:
- SA impersonation: `gcloud auth login --impersonate-service-account=SA` → ADC file stays `authorized_user` type
- Python impersonation: `google.auth.impersonated_credentials.Credentials()` → 403 on acquire
- Direct ADC: `gcloud auth application-default login --scopes=cloud-platform` → token has scopes but `google.auth.default()` loses them
- **Resolution: Stay on SA JSON.** It works reliably on Aliyun with the rate limiter.

## Related

- `references/platform-dots-mangling.md` — `...` mangling in Hermes→SSH terminal commands
- `gemini-api-resilience-wrapper` skill — umbrella for all Gemini resilience patterns
