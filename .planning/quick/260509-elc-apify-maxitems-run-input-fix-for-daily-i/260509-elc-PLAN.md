---
phase: 260509-elc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingest_wechat.py
  - tests/unit/test_apify_run_input.py
autonomous: true
requirements:
  - APIFY-MAXITEMS-01
must_haves:
  truths:
    - "Apify pay-per-result actor zOQWQaziNeBNFWN1O receives a non-zero max_items run-option on every invocation"
    - "Existing dual-token rotation behavior (F1a) is preserved — primary→backup fallback still works unchanged"
    - "WeChat URL = 1 expected article, so max_items=1 is correct (one article in startUrls → one item out)"
    - "No live Apify network calls are issued during pytest"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "_apify_call passes max_items=1 as a kwarg on .call()"
      contains: ".call(run_input=run_input, max_items=1)"
    - path: "tests/unit/test_apify_run_input.py"
      provides: "Unit test asserting max_items=1 is passed to ApifyClient.actor(...).call() kwargs"
      contains: "max_items"
  key_links:
    - from: "ingest_wechat.py:_apify_call"
      to: "apify_client.ActorClient.call"
      via: "max_items kwarg (run-level option, NOT a run_input dict key)"
      pattern: "\\.call\\(run_input=run_input, max_items=1\\)"
    - from: "tests/unit/test_apify_run_input.py"
      to: "ingest_wechat._apify_call"
      via: "monkeypatch ApifyClient class to capture .call() kwargs"
      pattern: "max_items.*==.*1"
---

<objective>
Fix the 2026-05-08 09:00 ADT daily-ingest cron failure where 5/5 articles errored with "Maximum charged results must be greater than zero". Apify pay-per-result actor `zOQWQaziNeBNFWN1O` rejects runs without a non-zero `max_items` run-option. Add `max_items=1` to the single `.call()` invocation in `_apify_call` and back the change with a unit test that verifies the kwarg is actually passed (mocking ApifyClient — zero network).

Purpose: Unblock daily-ingest cron. Pay-per-result actors require this run-option per the apify-client SDK (`apify_client/clients/resource_clients/actor.py:316-372` — `max_items` kwarg maps to API field `maxItems`). WeChat URL = 1 article expected.

Output:
- 1-line code change at ingest_wechat.py:574
- New test file tests/unit/test_apify_run_input.py asserting `max_items=1` reaches `.call()`
- Atomic commit with forensic citations (cron session JSON, bug report, SDK source line)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@ingest_wechat.py
@tests/unit/test_apify_rotation.py

<interfaces>
<!-- Verified from venv/Lib/site-packages/apify_client/clients/resource_clients/actor.py:316-372 -->
<!-- ActorClient.call() signature (synchronous, what _apify_call uses): -->

```python
class ActorClient(ResourceClient):
    def call(
        self,
        run_input: Any = None,
        *,
        content_type: str | None = None,
        build: str | None = None,
        max_items: int | None = None,           # ← run-level option, maps to API "maxItems"
        max_total_charge_usd: Decimal | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        webhooks: list[dict] | None = None,
        wait_secs: int | None = None,
        logger: logging.Logger | None | Literal['default'] = 'default',
    ) -> dict | None:
        '''
        ...
        max_items: Maximum number of results that will be returned by this run.
            If the Actor is charged per result, you will not be charged for more
            results than the given limit.
        ...
        '''
```

Internally (line 371-372): `if max_items is not None: request_params['maxItems'] = max_items`.

Current call site (ingest_wechat.py:574, the lambda inside `loop.run_in_executor`):

```python
future = loop.run_in_executor(
    None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input)
)
```

Required form (this plan):

```python
future = loop.run_in_executor(
    None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input, max_items=1)
)
```

Note: `max_items` is a kwarg on `.call()`, NOT a key inside the `run_input` dict. The user's task description hypothesis ("在 run_input 里加 maxItems") was verified WRONG — see verified_findings in the planning prompt and the SDK source above.
</interfaces>

<forensic_evidence>
- Cron session: `session_cron_2b7a8bee53e0_20260508_090038.json` (Hermes-side artifact)
- Bug report: `docs/bugreports/2026-05-08-cron-ingest-failure.md`
- Error message (exact): `"Maximum charged results must be greater than zero"`
- 5/5 article failures on 2026-05-08 09:00 ADT cron — ALL hit this same error before falling through cascade to UA (which also failed; that is a separate concern out of scope here)
- SDK source: `apify_client/clients/resource_clients/actor.py:322` (declares `max_items: int | None = None`); line 371-372 (maps to `request_params['maxItems']`)
</forensic_evidence>

<scope_boundary>
HARD scope — parallel ir-4 W2 agent owns batch_ingest_from_spider.py + lib/scraper.py:
- ALLOWED: ingest_wechat.py:_apify_call (specifically line 574, the lambda)
- ALLOWED: tests/unit/test_apify_run_input.py (NEW file)
- FORBIDDEN: batch_ingest_from_spider.py, lib/scraper.py, any migration / SQL / Layer 1 / Layer 2 code
</scope_boundary>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write unit test asserting max_items=1 reaches ApifyClient.actor(...).call() kwargs</name>
  <files>tests/unit/test_apify_run_input.py</files>
  <behavior>
    NEW test file `tests/unit/test_apify_run_input.py`. Sibling to existing `tests/unit/test_apify_rotation.py`. The existing rotation test mocks `_apify_call` directly (one level too high to verify the `.call()` kwargs we care about). This new test mocks one level deeper — at the `ApifyClient` class — so we can capture the actual kwargs passed to `.call()`.

    Test: `test_apify_call_passes_max_items_1`
    - Arrange: monkeypatch `ingest_wechat.ApifyClient` with a fake class whose `actor(actor_id)` returns an object whose `.call(...)` records all kwargs into a captured dict and returns a synthetic run dict (e.g. `{"defaultDatasetId": "ds-fake"}`). Also stub `client.dataset(...).iterate_items()` to return one minimal item dict.
    - Act: `await ingest_wechat._apify_call(token="t", url="https://mp.weixin.qq.com/s/fake")`
    - Assert (the contract this test exists to enforce):
      1. `.call()` was invoked exactly once
      2. `max_items` kwarg was present on that call
      3. `max_items == 1` (NOT 0, NOT None — pay-per-result actor would reject those)
      4. `run_input` kwarg was passed and its shape is unchanged (still has `startUrls` + `crawlerConfig`) — no fields moved INTO run_input
      5. `actor()` was called with the actor ID `"zOQWQaziNeBNFWN1O"` (regression guard against accidental ID drift)

    Pattern to follow: `tests/unit/test_apify_rotation.py` — `pytest.mark.asyncio`, monkeypatch on the `ingest_wechat` module, no live network. Use a small fake class (not unittest.mock.MagicMock) so the captured kwargs are easy to assert against directly.

    No `print()` in the test code — use plain assertions (per python rules, prefer logging/assertions over print in production-like code; tests just assert).

    NOTE: this test will FAIL on the unmodified codebase (current line 574 does NOT pass max_items). That is the intended RED state. Task 2 makes it GREEN.
  </behavior>
  <action>
    Create `tests/unit/test_apify_run_input.py`. Follow the structure and idioms of `tests/unit/test_apify_rotation.py` (pytest.mark.asyncio, monkeypatch on the `ingest_wechat` module). Mock at the `ApifyClient` level — replace `ingest_wechat.ApifyClient` with a fake class whose `.actor(actor_id).call(...)` records kwargs into a captured dict and returns `{"defaultDatasetId": "ds-fake"}`. Also stub `client.dataset(...).iterate_items()` to yield one item dict so `_apify_call`'s post-processing returns a non-None result.

    Run the test against the unmodified codebase to confirm RED: `pytest tests/unit/test_apify_run_input.py -x -v`. Expect the `max_items` assertion to fail (because line 574 does not yet pass it). Capture this RED output mentally — do NOT commit a passing-on-broken-code test.

    Do NOT modify `ingest_wechat.py` in this task. Task 2 owns that change.
  </action>
  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_apify_run_input.py -x -v</automated>
  </verify>
  <done>
    Test file exists at `tests/unit/test_apify_run_input.py` with one async test `test_apify_call_passes_max_items_1`. Running pytest on the unmodified codebase shows the test FAILS on the `max_items == 1` assertion (RED state confirmed — proves the test actually exercises the code path under change). Existing `tests/unit/test_apify_rotation.py` is untouched and still passes.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add max_items=1 kwarg to the .call() invocation in _apify_call (turns RED → GREEN)</name>
  <files>ingest_wechat.py</files>
  <action>
    Edit `ingest_wechat.py` line 574 only. Surgical 1-line change inside the lambda passed to `loop.run_in_executor`:

    BEFORE:
    ```python
        future = loop.run_in_executor(
            None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input)
        )
    ```

    AFTER:
    ```python
        future = loop.run_in_executor(
            None, lambda: client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input, max_items=1)
        )
    ```

    Rationale (NOT comment in code — body of commit message):
    - Apify pay-per-result actor `zOQWQaziNeBNFWN1O` rejects runs without non-zero `max_items` run-option per the SDK contract (`apify_client/clients/resource_clients/actor.py:322`, kwarg → API field `maxItems`).
    - WeChat URL = 1 expected article per call (one URL in `startUrls`), so value=1.
    - This is a RUN-LEVEL kwarg on `.call()`, NOT a key inside `run_input`. Verified: putting it inside the `run_input` dict has no effect (the actor SDK does not read run-level options from input).

    Do NOT touch:
    - The docstring of `_apify_call` (already accurate — only the call signature changed)
    - `scrape_wechat_apify` rotation logic at lines 592+
    - Any other call site (grep `client.actor(.*\\)\\.call\\(` to confirm there is only one — line 574)
    - Imports, module structure, or unrelated formatting

    After the edit: re-run the new test from Task 1. It should now PASS (GREEN). Also re-run the existing rotation test to confirm zero regression.
  </action>
  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_apify_run_input.py tests/unit/test_apify_rotation.py -x -v</automated>
  </verify>
  <done>
    Line 574 of `ingest_wechat.py` contains `client.actor("zOQWQaziNeBNFWN1O").call(run_input=run_input, max_items=1)`. New test `test_apify_call_passes_max_items_1` PASSES (GREEN). All three existing rotation tests in `test_apify_rotation.py` still PASS (no regression — F1a dual-token rotation behavior preserved). No other lines of `ingest_wechat.py` were modified. `grep -n "\\.call(" ingest_wechat.py` shows exactly one Apify `.call()` invocation, and it carries `max_items=1`.
  </done>
</task>

</tasks>

<verification>
After both tasks complete:

1. Diff is exactly 1 line changed in `ingest_wechat.py` plus 1 new test file. Run:
   ```bash
   git diff --stat ingest_wechat.py
   # Expect: 1 file changed, 1 insertion(+), 1 deletion(-)
   git status tests/unit/test_apify_run_input.py
   # Expect: untracked (new file)
   ```

2. Both test files green:
   ```bash
   .venv/Scripts/python -m pytest tests/unit/test_apify_run_input.py tests/unit/test_apify_rotation.py -v
   ```

3. Scope check (FORBIDDEN files untouched):
   ```bash
   git status batch_ingest_from_spider.py lib/scraper.py
   # Expect: no changes (parallel ir-4 W2 agent owns these)
   ```

4. No secrets in diff:
   ```bash
   git diff ingest_wechat.py | grep -iE "(token|key|secret|apify_api_)" || echo "OK — no literal secrets"
   ```

5. Atomic commit (forward-only, no rebase/amend/force):
   ```bash
   git add ingest_wechat.py tests/unit/test_apify_run_input.py
   git commit -m "$(cat <<'EOF'
   fix(scraper-260509-apify): add max_items=1 to Apify .call() to unblock pay-per-result actor

   The 2026-05-08 09:00 ADT daily-ingest cron failed 5/5 articles with
   "Maximum charged results must be greater than zero" because the
   pay-per-result actor zOQWQaziNeBNFWN1O rejects runs without a non-zero
   max_items run-option.

   Fix: pass max_items=1 as a kwarg on ApifyClient.actor(...).call() in
   _apify_call (ingest_wechat.py:574). WeChat URL = 1 article expected per
   call (one URL in startUrls), so max_items=1 is the correct value.

   Note: max_items is a RUN-LEVEL option (kwarg on .call()), NOT a key
   inside the run_input dict — verified against the apify-client Python
   SDK source at apify_client/clients/resource_clients/actor.py:322 where
   max_items is declared and line 371-372 where it maps to the API field
   maxItems.

   Forensic evidence:
   - Cron session: session_cron_2b7a8bee53e0_20260508_090038.json
   - Bug report: docs/bugreports/2026-05-08-cron-ingest-failure.md
   - Error (exact): "Maximum charged results must be greater than zero"
   - SDK source: apify_client/clients/resource_clients/actor.py:322

   Tests:
   - NEW: tests/unit/test_apify_run_input.py — mocks ApifyClient class
     and asserts .call() receives max_items=1 plus unchanged run_input
     shape; zero live network calls
   - REGRESSION: tests/unit/test_apify_rotation.py (F1a dual-token) all
     three tests still pass — rotation behavior preserved
   EOF
   )"
   ```

6. Confirm commit landed (forward-only, NO push without operator approval):
   ```bash
   git log -1 --stat
   # Expect: 2 files changed; ingest_wechat.py +1/-1; test_apify_run_input.py new
   ```
</verification>

<success_criteria>
- [ ] `ingest_wechat.py` line 574 contains `max_items=1` as a kwarg on `.call()`
- [ ] `max_items` is NOT a key inside `run_input` (correct architectural placement per SDK contract)
- [ ] `tests/unit/test_apify_run_input.py` exists with one async test that mocks ApifyClient and asserts `max_items=1` reaches `.call()` kwargs
- [ ] Running pytest on the new test file PASSES after Task 2
- [ ] Existing `tests/unit/test_apify_rotation.py` still PASSES (3/3 — zero regression)
- [ ] Diff is exactly 2 files: 1-line change in ingest_wechat.py + new test file
- [ ] FORBIDDEN files (batch_ingest_from_spider.py, lib/scraper.py) untouched
- [ ] Single atomic commit with prefix `fix(scraper-260509-apify):` citing cron session JSON, bug report path, exact error message, and SDK source line
- [ ] No literal secrets/tokens/keys in code or commit message
- [ ] No git stash/reset/rebase/amend/force-push used
- [ ] No live Apify network call issued during pytest (mock-only)
</success_criteria>

<output>
After completion, create `.planning/quick/260509-elc-apify-maxitems-run-input-fix-for-daily-i/260509-elc-SUMMARY.md` documenting:
- Diff applied (file paths + line numbers)
- Pytest output proving GREEN on new test + zero regression on rotation tests
- Commit SHA + first line of commit message
- Confirmation that forbidden files (batch_ingest_from_spider.py, lib/scraper.py) were not touched
</output>
