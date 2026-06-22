---
quick_id: 260522-em8
description: SSG-bake body prompt + hardcode deepseek-v4-pro for body translate
date: 2026-05-22
status: completed
---

# Quick Task 260522-em8: SUMMARY

## What changed

### `lib/llm_deepseek.py`

- `deepseek_model_complete` gains optional `model: str | None = None` parameter.
- When `model` is `None` (the default), behavior is unchanged — uses
  module-level `_MODEL` from `DEEPSEEK_MODEL` env. LightRAG callers continue to
  pass nothing.
- When `model` is provided (e.g. `"deepseek-v4-pro"`), it overrides for that
  single call only. Docstring updated to document the override.

### `lib/translate.py`

- Module docstring lines 16-18 replaced: R7 image-positioning language → SSG-bake
  discipline disclosure (boilerplate strip, H1 demotion, alt-text enrichment,
  code-fence inference, paragraph splitting).
- New module-level constant `_BAKE_MODEL = "deepseek-v4-pro"` after the timeout
  constants, with comment explaining it is independent of `DEEPSEEK_MODEL` env
  (which still governs LightRAG callers).
- `_build_body_prompt` rewritten as a 7-rule SSG-bake brief:
  1. Headings — never output H1, demote source H1 to H2.
  2. WeChat boilerplate strip — 关注公众号 / 点赞 / 在看 / 二维码 / 转载声明 /
     作者简介尾段 sections at body end.
  3. Lead filler strip — opening sentences like "今天我们来聊", "大家好",
     "本文将介绍".
  4. Image references — preserve exact line/paragraph position; translate or
     generate descriptive alt text in target_lang; URL verbatim.
  5. Code blocks — verbatim, content untranslated; infer language tag for
     unlabeled fences (python / bash / json / yaml).
  6. Long paragraphs (~>200 chars) — split at logical sentence boundaries.
  7. Output ONLY baked markdown — no preamble.
- `translate_body_with_deepseek_tavily` body call site now passes
  `deepseek_model_complete(prompt, model=_BAKE_MODEL)`. Title path unchanged.

## What did NOT change (per plan non-goals)

- `translate_title_with_deepseek_tavily` — title path unchanged; still uses env
  `DEEPSEEK_MODEL` (default `deepseek-v4-flash`).
- `BodyTranslationResult` TypedDict — unchanged.
- `detect_source_lang` — unchanged.
- No gate, no `DEEPSEEK_REPORT` parsing, no new env vars.

## Verification

Smoke command from plan executed locally:

```
$ venv/Scripts/python.exe -c "
from lib.translate import translate_body_with_deepseek_tavily, _BAKE_MODEL
from lib.llm_deepseek import deepseek_model_complete
import inspect
sig = inspect.signature(deepseek_model_complete)
assert 'model' in sig.parameters, 'model param missing'
assert _BAKE_MODEL == 'deepseek-v4-pro'
print('ok:', _BAKE_MODEL)
"
ok: deepseek-v4-pro
```

Both module-level imports succeed, signature inspection confirms `model`
parameter is present on `deepseek_model_complete`, and `_BAKE_MODEL` resolves
to the expected `"deepseek-v4-pro"`.

## Commit

```
feat(translate/bake): SSG-bake body prompt — H1-demote, boilerplate strip, alt-text enrich, paragraph split; hardcode deepseek-v4-pro
```

## Follow-ups

- End-to-end bake test (3-5 mixed zh/en articles → run body translate path on
  Hermes prod where DeepSeek is reachable; corp network blocks it locally) is
  the next step. User will drive via Hermes prompt — see chat for the prompt.
