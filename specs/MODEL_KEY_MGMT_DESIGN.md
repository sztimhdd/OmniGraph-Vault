# Model & Key Management Design

> **Status:** Design — not yet scheduled as a phase. Consolidated from research on Hermes/OpenClaw conventions, Gemini API behavior, and Python async patterns.
> **Goal:** Replace scattered `GEMINI_API_KEY` reads, hardcoded model strings, and one-off rate limiters with a single shared library — while staying compatible with Hermes and OpenClaw skill conventions.

---

## 1. Problem Statement

The current solution is self-sufficient for model calls (direct Gemini API, no Hermes model router involvement) but **primitively so** — the pieces are duplicated across scripts and inconsistent:

- **Model strings hardcoded** in ~18 files — `gemini-2.5-flash-lite` in ingest_wechat.py, `gemini-3.1-flash-lite-preview` in ingest_github.py (already drifted)
- **Single API key**, single env var name (`GEMINI_API_KEY`) — no rotation, hard stop on quota exhaustion
- **Rate limiting lives in one script** — `ingest_wechat.py` has `_LLM_MIN_INTERVAL=15.0` + asyncio.Lock; other scripts have none
- **No retry layer** on top of google-genai SDK calls — 429 errors bubble up and crash jobs
- **`GEMINI_API_KEY` is generically named** — collides with Hermes's own LLM calls and other skills on the same host

---

## 2. Research Findings

### 2.1 Hermes Agent conventions

**Where secrets live:** `~/.hermes/.env` or `os.environ`.

**How skills declare secrets** — in SKILL.md frontmatter:

```yaml
required_environment_variables:
  - name: OMNIGRAPH_GEMINI_KEY
    prompt: "Gemini API key (get from https://aistudio.google.com/apikey)"
    help: "Used for LLM, embedding, and vision calls in OmniGraph-Vault"
    required_for: full functionality
```

**Runtime behavior:** On `skill_view`, declared vars are auto-registered for passthrough into `execute_code` and terminal sandboxes. Skills' scripts can read them via `os.environ` directly.

**Security model:** `execute_code` strips API keys/tokens by default. Only **explicitly declared** vars pass through. Reference: [Hermes Security docs](https://hermes-agent.nousresearch.com/docs/user-guide/security).

**Known gaps** (from GitHub issues):
- [#410](https://github.com/NousResearch/hermes-agent/issues/410): no per-skill scoping — all declared secrets available to all tools equally
- [#3433](https://github.com/NousResearch/hermes-agent/issues/3433): declared vars not passed through correctly for remote-backed sessions (daytona, docker)

Implication: declare scoped names (`OMNIGRAPH_GEMINI_KEY`), don't rely on Hermes to enforce isolation.

### 2.2 OpenClaw conventions

**SKILL.md frontmatter:**

```yaml
metadata:
  openclaw:
    skillKey: omnigraph-vault
    primaryEnv: OMNIGRAPH_GEMINI_KEY
    requires:
      config: [OMNIGRAPH_GEMINI_KEY]
```

**Config file** (`~/.openclaw/openclaw.json`):

```json
{
  "skills": {
    "entries": {
      "omnigraph-vault": {
        "enabled": true,
        "apiKey": "AIza...",
        "env": {
          "OMNIGRAPH_GEMINI_KEY": "AIza...",
          "OMNIGRAPH_GEMINI_KEYS": "AIza..._proj1,AIza..._proj2"
        }
      }
    }
  }
}
```

- `apiKey` is a convenience — auto-sets the `primaryEnv` var
- `env` injects per-skill vars into the subprocess, **but only if not already set in the process**
- Supports plaintext OR `SecretRef` (`{ source, provider, id }`) for keychain integration
- OpenClaw **does** scope per-skill (unlike Hermes today)

### 2.3 Gemini API critical constraint

> **Gemini rate limits are per-project, not per-key.** All keys under the same Google Cloud project share the same quota pool. To actually bypass limits via rotation, you need keys from **different Google accounts** or **different projects**.

Sources: [Apiyi 429 guide](https://help.apiyi.com/en/gemini-3-1-pro-429-rate-limit-quota-exceeded-fix-guide-en.html), [Medium: simple key rotation](https://medium.com/@castnutt/avoid-gemini-api-rate-limits-with-simple-key-rotation-python-f47b0dacb168).

**Implication:** `OMNIGRAPH_GEMINI_KEYS` rotation is **only useful if the user has multiple GCP projects or Google accounts**. For a single-account user, rotation does nothing — the design must make this explicit in docs and not imply otherwise.

### 2.4 Python async patterns

- **Rate limiting**: `aiolimiter.AsyncLimiter(max_rate, time_period)` — leaky bucket, async-native. Standard choice. Already battle-tested. Dependency: `aiolimiter` (~30KB, zero transitive deps).
- **Retry**: `tenacity` — standard choice, handles async, has `retry_if_exception`, `wait_exponential`. Dependency: `tenacity` (~100KB).
- **Exception to retry on**: `google.genai.errors.APIError` with `.code in {429, 503}`. **NOT** `google.api_core.exceptions.ResourceExhausted` — that's the deprecated `google.generativeai` SDK. The new `google-genai` SDK (which we use) raises `APIError`. Source: [python-genai #1427](https://github.com/googleapis/python-genai/issues/1427), [SO answer](https://stackoverflow.com/questions/78758029/i-got-the-error-google-api-core-exceptions-resourceexhausted-429-resource-has).

Use `retry_if_exception` with a predicate (not `retry_if_exception_type`) so non-retriable codes (400, 401, 403) aren't retried.

Canonical composition:

```python
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from google.genai.errors import APIError

def _is_retriable(exc: BaseException) -> bool:
    return isinstance(exc, APIError) and getattr(exc, "code", None) in {429, 503}

_limiter = AsyncLimiter(max_rate=15, time_period=60)  # 15 RPM for flash-lite free tier

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def call(...):
    async with _limiter:
        ...
```

### 2.5 Gemini free-tier rate limits (verified April 2026)

Post-December-2025 reduction. Source: [Google AI rate limits docs](https://ai.google.dev/gemini-api/docs/rate-limits), [AI Free API April 2026 guide](https://www.aifreeapi.com/en/posts/gemini-api-free-tier-complete-guide).

| Model | Free RPM | Free RPD | Tier 1 RPM |
|---|---|---|---|
| `gemini-2.5-pro` | 5 | 100 | 150 |
| `gemini-2.5-flash` | 10 | 250 | 150 |
| `gemini-2.5-flash-lite` | **15** | 1,000 | 300 |
| `gemini-3.1-pro-preview` | no free tier | n/a | — |
| `gemini-embedding-001` | **not publicly documented** | — | — |

**Implication:** since our primary model (`gemini-2.5-flash-lite`) has the highest free-tier quota at 15 RPM / 1,000 RPD, we should design around that rather than the conservative 4 RPM we currently use in `ingest_wechat.py`. The embedding RPM requires manual verification in AI Studio per-project.

---

## 3. Locked Design Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Canonical env var: `OMNIGRAPH_GEMINI_KEY` | Namespaced, won't collide with Hermes or other skills |
| D2 | Fallback: `GEMINI_API_KEY` if scoped name unset | Keeps dev/standalone ergonomics; google-genai SDK's own default |
| D3 | Optional rotation: `OMNIGRAPH_GEMINI_KEYS` (comma-separated) | Only helpful with multi-project keys; clearly documented |
| D4 | On key exhaustion: rotate to next key, retry; all keys exhausted → exponential backoff | Matches Gemini's per-project quota semantics |
| D5 | New module: `lib/` at repo root | Simple path; importable from all existing scripts |
| D6 | Dependencies: add `aiolimiter` + `tenacity` to `requirements.txt` | ~130KB combined; standard choices |
| D7 | Model registry: `lib/models.py` as string constants | Enum is overkill; constants are greppable |
| D8 | Rate limiter: one `AsyncLimiter` per **model name**, shared across modules via module-level singleton | Flash and Pro have different RPMs; per-model is natural |
| D9 | SKILL.md: declare BOTH Hermes and OpenClaw metadata | One codebase, two host conventions |
| D10 | Migration: `lib/` lands first + `ingest_wechat.py` migrates first as reference; then other files in follow-up PRs | Minimizes blast radius of any bug |

---

## 4. Proposed Module Layout

```
lib/
├── __init__.py
├── models.py          # string constants: INGESTION_LLM, VISION_LLM, EMBEDDING_MODEL, SYNTHESIS_LLM
├── api_keys.py        # load + rotate: OMNIGRAPH_GEMINI_KEY → GEMINI_API_KEY → OMNIGRAPH_GEMINI_KEYS pool
├── rate_limit.py      # per-model AsyncLimiter registry
└── llm_client.py      # async generate(model, prompt, ...) — wraps google-genai with rate limit + retry + rotation
```

### 4.1 `lib/models.py`

```python
"""Central registry of model names. Change once, propagates everywhere."""

# LLM for entity extraction, summarization, ingestion-side generation
INGESTION_LLM = "gemini-2.5-flash-lite"

# LLM for image description (vision-capable)
VISION_LLM = "gemini-2.5-flash-lite"

# LLM for knowledge-graph synthesis at query time (higher quality OK)
SYNTHESIS_LLM = "gemini-2.5-flash-lite"

# Embedding model — changing this requires re-embedding everything
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
EMBEDDING_MAX_TOKENS = 2048

# RPM caps per model. Free tier, verified April 2026 (post-Dec-2025 reduction).
# Override via env OMNIGRAPH_RPM_<MODEL> if on paid tier. Embedding RPM is not
# publicly documented — verify in AI Studio per project before setting.
RATE_LIMITS_RPM = {
    "gemini-2.5-pro":        5,
    "gemini-2.5-flash":      10,
    "gemini-2.5-flash-lite": 15,   # our primary
    "gemini-embedding-001":  60,   # conservative guess — verify per project!
}
```

### 4.2 `lib/api_keys.py`

```python
"""Gemini API key loader with optional rotation pool."""
import itertools
import os
from typing import Iterator

_PRIMARY_VAR = "OMNIGRAPH_GEMINI_KEY"
_FALLBACK_VAR = "GEMINI_API_KEY"       # SDK default, also for standalone dev
_POOL_VAR = "OMNIGRAPH_GEMINI_KEYS"     # comma-separated, optional

def load_keys() -> list[str]:
    """Load Gemini API keys in precedence order. Never empty — raises on total absence."""
    pool = os.environ.get(_POOL_VAR, "").strip()
    if pool:
        return [k.strip() for k in pool.split(",") if k.strip()]
    single = os.environ.get(_PRIMARY_VAR) or os.environ.get(_FALLBACK_VAR)
    if single:
        return [single]
    raise RuntimeError(
        f"No Gemini API key found. Set {_PRIMARY_VAR} (preferred), "
        f"{_FALLBACK_VAR}, or {_POOL_VAR} (comma-separated for rotation)."
    )

_cycle: Iterator[str] | None = None
_current: str | None = None


def _init_cycle() -> None:
    global _cycle, _current
    if _cycle is None:
        _cycle = itertools.cycle(load_keys())
        _current = next(_cycle)


def current_key() -> str:
    """Get the currently active key."""
    _init_cycle()
    assert _current is not None
    return _current


def rotate_key() -> str:
    """Advance to the next key in the pool (round-robin). Call on 429/503."""
    global _current
    _init_cycle()
    _current = next(_cycle)  # type: ignore[arg-type]
    return _current
```

### 4.3 `lib/rate_limit.py`

```python
"""Per-model rate limiters, shared across the whole process."""
from aiolimiter import AsyncLimiter
from .models import RATE_LIMITS_RPM

_limiters: dict[str, AsyncLimiter] = {}

def get_limiter(model: str) -> AsyncLimiter:
    """Get or create a shared limiter for this model."""
    if model not in _limiters:
        rpm = RATE_LIMITS_RPM.get(model, 4)  # conservative default
        _limiters[model] = AsyncLimiter(max_rate=rpm, time_period=60)
    return _limiters[model]
```

### 4.4 `lib/llm_client.py`

```python
"""The single place where Gemini LLM calls happen. Rate-limited, retried, key-rotated.

Uses the new google-genai SDK (`google.genai`). Do NOT use the deprecated
google.generativeai SDK (that one raises google.api_core.exceptions.ResourceExhausted
on 429; the new SDK raises google.genai.errors.APIError with .code == 429).
"""
from google import genai
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .api_keys import current_key, rotate_key
from .rate_limit import get_limiter


def _is_retriable(exc: BaseException) -> bool:
    """429 (rate limit) and 503 (server overload) are retriable; 4xx auth/validation errors are not."""
    return isinstance(exc, APIError) and getattr(exc, "code", None) in {429, 503}


# Client cache: recreate only when the active key rotates.
_client: genai.Client | None = None
_client_key: str | None = None


def _get_client() -> genai.Client:
    global _client, _client_key
    key = current_key()
    if _client is None or _client_key != key:
        _client = genai.Client(api_key=key)
        _client_key = key
    return _client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retriable),
    reraise=True,
)
async def generate(model: str, prompt: str, **kwargs) -> str:
    """Generate text. Rate-limited per-model, retried w/ backoff on 429/503, rotates key on each retry."""
    async with get_limiter(model):
        try:
            response = await _get_client().aio.models.generate_content(
                model=model, contents=prompt, **kwargs
            )
            return response.text
        except APIError as e:
            if _is_retriable(e):
                rotate_key()  # advance key so next retry uses a different one
            raise
```

(An `embed(texts)` helper and a vision `describe_image(model, image)` helper follow the same pattern.)

### 4.5 SKILL.md frontmatter — dual-host declaration

```yaml
---
name: omnigraph_ingest
description: "Ingest WeChat articles and PDFs into the knowledge graph"
triggers: [...]

# --- Hermes ---
required_environment_variables:
  - name: OMNIGRAPH_GEMINI_KEY
    prompt: "Gemini API key for OmniGraph-Vault"
    help: "Get from https://aistudio.google.com/apikey"
    required_for: full functionality

# --- OpenClaw ---
metadata:
  openclaw:
    skillKey: omnigraph-vault
    primaryEnv: OMNIGRAPH_GEMINI_KEY
    requires:
      bins: ["python"]
      config: [OMNIGRAPH_GEMINI_KEY]
    os: ["darwin", "linux", "win32"]
---
```

---

## 5. Migration Plan

Files that touch Gemini directly today (from grep of production code, ~18 files):

| # | File | # occurrences | Priority |
|---|---|---|---|
| 1 | `ingest_wechat.py` | 10+ | P0 — reference migration |
| 2 | `multimodal_ingest.py` | 11 | P0 |
| 3 | `ingest_github.py` | 8 | P0 |
| 4 | `query_lightrag.py` | 8 | P0 |
| 5 | `kg_synthesize.py` | ~5 | P0 |
| 6 | `cognee_wrapper.py` | 9 | P1 |
| 7 | `cognee_batch_processor.py` | 7 | P1 |
| 8 | `enrichment/extract_questions.py` | 1 | P1 |
| 9 | `enrichment/fetch_zhihu.py` | 2 | P1 |
| 10 | `enrichment/merge_and_ingest.py` | 2 | P1 |
| 11 | `batch_classify_kol.py` | 3 | P2 |
| 12 | `batch_ingest_from_spider.py` | 4 | P2 |
| 13 | `batchkol_topic.py` | 3 | P2 |
| 14 | `_reclassify.py` | — | P2 |
| 15 | `config.py` | 12 | P0 — cross-cutting |
| 16 | `setup_cognee.py` / `init_cognee.py` | — | P2 |
| 17 | `tests/verify_gate_{a,b,c}.py` | — | P2 |
| 18 | `skill_runner.py` | — | P2 |

**Execution order:**

1. Land `lib/` module + tests (no call sites change yet)
2. Migrate `ingest_wechat.py` as the reference — proves the pattern end-to-end
3. Migrate P0 files (ingest, query, synthesize) — core user flow
4. Migrate P1 (Cognee, enrichment) — supporting flows
5. Migrate P2 (batch scripts, tests) — cleanup

Each step is independently shippable; nothing is "half-migrated" after a commit.

---

## 6. Success Criteria

- [ ] **Model change is one edit.** Changing `INGESTION_LLM` in `lib/models.py` propagates to every script without further edits.
- [ ] **Key rotation demonstrably works.** With two keys in `OMNIGRAPH_GEMINI_KEYS`, deliberately revoking one mid-run causes a single retry and continues on the other key. (Only testable if user has multi-project keys.)
- [ ] **429 recovery works.** Injecting a simulated `ResourceExhausted` causes exponential backoff + retry, not a crash.
- [ ] **All existing tests pass.** `python skill_runner.py skills/ --test-all` green.
- [ ] **Scoped env var used in deployment.** Hermes PC has `OMNIGRAPH_GEMINI_KEY` set in `~/.hermes/.env`; corp laptop can still use `GEMINI_API_KEY` for local dev.
- [ ] **SKILL.md dual-host metadata validated.** `hermes skills list` and `openclaw skills list` (where available) both show the skill as ready with `OMNIGRAPH_GEMINI_KEY` recognized.

---

## 7. Open Questions for the User

1. **Do you have (or are willing to create) multiple Google accounts / GCP projects for rotation?** If not, `OMNIGRAPH_GEMINI_KEYS` rotation is pointless — same-project keys share the quota pool. We'd still ship the mechanism but the docs should say "single-user users: don't bother populating this."

2. **Migration scope — one phase or split?** Three options:
   - **All 18 files in one phase** (bigger blast radius, faster to "done")
   - **P0 files now, P1/P2 deferred** (ships the core pattern, minor scripts keep using old pattern for a while)
   - **Reference file only** (just `ingest_wechat.py`, then re-evaluate)

3. **Where does `lib/` live?** Options: repo-root `lib/` (simplest), `omnigraph_core/` (explicit), or nested under `skills/_shared/` (skill-local). I prefer repo-root `lib/` for simplicity — skills can import it directly.

4. **Keep or drop `config.py`?** Currently it loads `~/.hermes/.env` and exports paths. We'd refactor it to import from `lib/api_keys.py` and `lib/models.py` — but the file itself stays.

5. **Phase numbering?** This could be Phase 6 (new), or slotted before Phase 5 pipeline automation as a prerequisite. My read: it's a prerequisite for Phase 5 because the embedding-model switch there is trivially one line once `lib/models.py` exists.

---

## 7.1 User Decisions (2026-04-28)

1. **Multi-account rotation:** User has multiple Google accounts. Rotation is real (one key per account = one quota pool per account). Docs must show: "one key per Google account/project" for rotation to help.
2. **Migration scope:** **All 18 files in one phase.**
3. **`lib/` location:** Repo-root `lib/`, project-internal only, NOT exposed as a Hermes skill.
4. **`config.py`:** Kept, refactored to delegate key/model concerns to `lib/`.
5. **Phase numbering:** **Phase 7** (Phases 4, 5, 6 already scheduled: zhihu enrichment, pipeline automation, graphify addon).
6. **Override on locked decisions:** Google SDK rate-limit and exception-class lookup done — design doc updated to new `google-genai` SDK (APIError code 429/503), free-tier RPMs verified April 2026, all models now in `RATE_LIMITS_RPM` dict.

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Rotation looks like it helps but doesn't (same project) | High for single-user | Low — still safe default | Clear docs; default to single-key behavior |
| `aiolimiter` / `tenacity` pin conflicts | Low | Medium | Both have minimal deps; verify in venv before committing |
| Hermes env passthrough bug (#3433) hits remote sandboxes | Medium for future remote sessions | High if it hits | `lib/api_keys.py` reads `os.environ` directly; works in any env where the var is set somehow |
| Migration half-done leaves drift worse than before | Medium | Medium | Each commit migrates a complete file; no "TODO: finish" comments |
| Tests assume `GEMINI_API_KEY` and break on rename | Medium | Low | Fallback logic means both names work; test harness only updates if it's specifically checking the name |

---

## 9. Not In Scope

- Multi-vendor abstraction (OpenAI + Anthropic + Gemini through one interface) — future work, not today
- Encrypted key storage (keychain, Vault, etc.) — Hermes/OpenClaw hosts already handle this if needed
- Hermes per-skill scoping workaround — blocked on issue #410; we just declare scoped names and wait
- Cognee's internal LLM calls — Cognee is configured via its own env vars (`COGNEE_LLM_API_KEY`). We'll set `COGNEE_LLM_API_KEY = current_key()` in `cognee_wrapper.py` init; that's it.
