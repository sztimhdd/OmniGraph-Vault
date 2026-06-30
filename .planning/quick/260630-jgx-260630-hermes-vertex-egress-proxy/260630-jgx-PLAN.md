---
phase: 260630-jgx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - deploy/aliyun/systemd/omnigraph-vertex-proxy.service
  - /root/.hermes/.env (Aliyun, NOT repo)
  - /etc/systemd/system/omnigraph-vertex-proxy.service (Aliyun, NOT repo)
  - /etc/hosts (Aliyun, NOT repo)
autonomous: true
requirements: [ISSUE-75-mitigation]
gap_closure: false

must_haves:
  truths:
    - "A Python embedding call from Aliyun venv-aim1 with ALL_PROXY set returns dim=3072 (not timeout)"
    - "SA token refresh succeeds through the proxy (curl or python google.auth probe returns a token, not ConnectTimeout)"
    - "If SPIKE is GO: omnigraph-vertex-proxy.service is active on Aliyun and survives systemctl restart"
    - "If SPIKE is GO: DeepSeek/SiliconFlow calls are NOT routed through Hermes (NO_PROXY exempts them)"
    - "If SPIKE is GO: KB_SYNTHESIZE_TIMEOUT is reverted to 240 in Aliyun kb-api override.conf"
    - "If SPIKE is NO-GO: Aliyun state is clean — no leftover tunnels, no .env modifications, DECISION.md records exact failure reason"
  artifacts:
    - path: "deploy/aliyun/systemd/omnigraph-vertex-proxy.service"
      provides: "Systemd unit (SOCKS5 egress tunnel Aliyun→Hermes, port 18080)"
      contains: "ssh.*-D.*18080"
    - path: ".planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md"
      provides: "SPIKE result (GO/NO-GO), rollback procedure, IT handoff trigger"
  key_links:
    - from: "Aliyun /root/.hermes/.env ALL_PROXY=socks5h://127.0.0.1:18080"
      to: "omnigraph-vertex-proxy.service SOCKS5 listener on 127.0.0.1:18080"
      via: "systemd service running ssh -D 127.0.0.1:18080 to Hermes"
      pattern: "omnigraph-vertex-proxy"
    - from: "Aliyun /root/.hermes/.env NO_PROXY"
      to: "api.deepseek.com,siliconflow.cn bypass"
      via: "env var read by requests + httpx trust_env=True"
      pattern: "NO_PROXY"
---

<objective>
Unblock Aliyun's dead Vertex/Google API path (#75 — ACK NetworkPolicy) by routing Google
traffic through a Hermes SSH SOCKS5 egress proxy as a temporary mitigation.

Purpose: 336 articles are stuck (173 layer1_verdict=NULL + every-2h ingest cron dies with
TransportError oauth2.googleapis.com ConnectTimeout). IT is fixing the ACK NetworkPolicy but
timeline is unclear. This proxy workaround restores embedding + classify in hours, not days.

Output:
- Phase 1 (SPIKE): Prove tunnel works end-to-end before committing any persistent changes
- Phase 2 (IMPLEMENT, only if SPIKE is GO): systemd unit + .env change + kb-api timeout revert
- DECISION.md documenting the result, rollback procedure, and IT handoff trigger

This is TEMPORARY. Full rollback when IT confirms ACK NetworkPolicy fix.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-RESEARCH.md

# Key environment facts (executor: operate these directly via Bash tool)
#
# Aliyun: ssh aliyun-vitaclaw (root@47.117.244.253:22, ~/.ssh/config alias)
# Hermes: ssh -p 49221 sztimhdd@ohca.ddns.net  (DO NOT write host/port/user to repo files)
# Aliyun venv: /root/OmniGraph-Vault/venv-aim1/bin/python
# Aliyun pip: /root/OmniGraph-Vault/venv-aim1/bin/pip
# Aliyun env: /root/.hermes/.env  (always `set -a; source /root/.hermes/.env; set +a` before Python)
# Aliyun kb-api override: /etc/systemd/system/kb-api.service.d/override.conf
#
# IMPORTANT: ssh -D creates a SOCKS5 server on Aliyun's loopback. Hermes is the SOCKS server.
# The tunnel direction is: Aliyun CONNECTS TO Hermes. Hermes proxies outbound requests for Aliyun.
# Hermes SSH port: see memory hermes_ssh.md (NOT written here per CLAUDE.md Principle #5).
#
# omnigraph-mcp-tunnel.service (existing) is the template for the new unit:
#   deploy/aliyun/systemd/omnigraph-mcp-tunnel.service
</context>

<interfaces>
<!-- Key files the executor needs to understand -->

From deploy/aliyun/systemd/omnigraph-mcp-tunnel.service (template to adapt):
```ini
[Unit]
Description=OmniGraph SSH tunnel: Aliyun localhost:8931 -> Hermes Playwright MCP (WeChat scrape fallback)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -N -T \
  -o ConnectTimeout=15 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new \
  -L 127.0.0.1:8931:localhost:8931 \
  hermes
Restart=always
RestartSec=10
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
```

Note: uses `hermes` as the SSH target (alias in ~/.ssh/config), NOT a literal host:port.
The new unit needs `-D 127.0.0.1:18080` instead of `-L`, same structure.

From /etc/systemd/system/kb-api.service.d/override.conf (REVERT KB_SYNTHESIZE_TIMEOUT here):
Contains: KB_SYNTHESIZE_TIMEOUT=30 (currently lowered from 240 as temp mitigation #75)
Target: KB_SYNTHESIZE_TIMEOUT=240 (revert after embedding recovers)
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: SPIKE — prove SOCKS5 proxy works for Vertex embedding + SA token refresh</name>
  <files>
    .planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md
  </files>
  <action>
Execute the spike end-to-end, then record the result in DECISION.md.

**Step A: Prerequisites (Aliyun)**

1. Install httpx[socks] on Aliyun venv-aim1 (required for google-genai httpx → socks5h):
   ```
   ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv-aim1/bin/pip install "httpx[socks]"'
   ```
   Expect: "Successfully installed socksio-1.*" (or "already satisfied").

2. Check for /etc/hosts Google pins (they must be removed before ANY socks5h test):
   ```
   ssh aliyun-vitaclaw 'grep -E "oauth2|aiplatform" /etc/hosts'
   ```
   If output is non-empty (lines found), remove them:
   ```
   ssh aliyun-vitaclaw "sed -i '/oauth2\.googleapis\.com/d; /aiplatform\.googleapis\.com/d; /us-central1-aiplatform\.googleapis\.com/d' /etc/hosts"
   ```
   Re-verify: `ssh aliyun-vitaclaw 'grep -E "oauth2|aiplatform" /etc/hosts'` → empty output.
   (socks5h bypasses /etc/hosts anyway, but removing them prevents socks5 vs socks5h confusion
    if code paths ever do local DNS resolution.)

**Step B: Open a TEMPORARY background tunnel (NOT systemd — this is just for the spike)**

Read the Hermes SSH host, port, and user from memory: ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md

Open the tunnel from Aliyun to Hermes using -D 18080:
```
ssh aliyun-vitaclaw 'nohup ssh \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes \
  -fN -D 127.0.0.1:18080 \
  -p <HERMES_PORT> <HERMES_USER>@<HERMES_HOST> \
  > /tmp/socks5-spike.log 2>&1'
```
Replace <HERMES_PORT>, <HERMES_USER>, <HERMES_HOST> from hermes_ssh.md. The `-f` flag
forks to background before executing, so the Aliyun nohup wrapper exits immediately.

Wait 3 seconds for SSH to establish, then verify port is bound:
```
ssh aliyun-vitaclaw 'ss -tlnp | grep 18080'
```
Expect: LISTEN on 127.0.0.1:18080. If not found, check /tmp/socks5-spike.log:
```
ssh aliyun-vitaclaw 'cat /tmp/socks5-spike.log'
```

**Step C: SA token refresh probe (curl)**

```
ssh aliyun-vitaclaw 'curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" \
  --socks5-hostname 127.0.0.1:18080 \
  https://oauth2.googleapis.com/token'
```
Expected: HTTP 400 or 404, < 2s. This proves the TCP path reaches Google via Hermes.
Anything other than a timeout IS a success here — 400 means POST required, 404 is fine.
A timeout (>10s) or "Connection refused" is a FAIL.

**Step D: Python embedding probe (the real gate)**

```
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
  set -a && source /root/.hermes/.env && set +a && \
  ALL_PROXY=socks5h://127.0.0.1:18080 \
  /root/OmniGraph-Vault/venv-aim1/bin/python -c "
import os
import asyncio
os.environ['"'"'ALL_PROXY'"'"'] = '"'"'socks5h://127.0.0.1:18080'"'"'
from lib.lightrag_embedding import lightrag_embedding_func
async def probe():
    result = await lightrag_embedding_func(['"'"'hermes proxy probe'"'"'])
    if result and len(result) > 0 and len(result[0]) > 0:
        print(f'"'"'EMBED OK dim={len(result[0])}'"'"')
    else:
        print('"'"'EMBED FAIL empty result'"'"')
asyncio.run(probe())
"'
```
Expected PASS: `EMBED OK dim=3072`
Expected FAIL examples: `TransportError`, `ConnectTimeout`, `ImportError: socksio`, `EMBED FAIL`

If socksio ImportError → Step A install did not apply to correct venv; re-check venv path.

**Step E: Kill the temporary tunnel (ALWAYS, regardless of result)**

```
ssh aliyun-vitaclaw 'pkill -f "ssh.*-D.*18080" || true'
```
Verify: `ssh aliyun-vitaclaw 'ss -tlnp | grep 18080'` → empty (port unbound).

**Step F: Record result in DECISION.md**

Create `.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md`
with the spike outcome. Include:
- Date/time, SPIKE result: GO or NO-GO
- curl probe result (http_code + time)
- embedding probe output verbatim
- If NO-GO: exact error message + why (e.g., socksio not found, Hermes SSH key rejected,
  Hermes can't reach aiplatform, etc.) + recommended next action
- Rollback note (for GO path): how to undo if IT fixes ACK NetworkPolicy
- IT trigger condition: when to rollback (IT confirms fix → verify wg show latest-handshake
  < 30s → remove ALL_PROXY/NO_PROXY + disable+stop service + revert KB_SYNTHESIZE_TIMEOUT)
- State of /etc/hosts (was it modified in Step A)
- KB_SYNTHESIZE_TIMEOUT status (currently 30, needs revert to 240 post-fix regardless)

**STOP HERE IF NO-GO.** Write DECISION.md with NO-GO result and exact failure reason.
Do NOT proceed to Task 2. Task 2 is gated on SPIKE GO.
  </action>
  <verify>
    <automated>
      # Verify DECISION.md exists and contains a result
      test -f ".planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md" && grep -E "SPIKE.*GO" ".planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-DECISION.md"

      # Verify temp tunnel is killed (run from local Bash tool, targeting Aliyun)
      # ssh aliyun-vitaclaw 'ss -tlnp | grep 18080' → must be empty

      # Verify httpx[socks] installed:
      # ssh aliyun-vitaclaw '/root/OmniGraph-Vault/venv-aim1/bin/pip show socksio' → shows Name: socksio
    </automated>
  </verify>
  <done>
    DECISION.md exists with SPIKE result (GO or NO-GO). Temporary tunnel is killed.
    If NO-GO: exact failure reason documented, Aliyun state clean (no lingering tunnels,
    no .env changes, no systend units). Task 2 NOT executed.
    If GO: embedding probe returned dim=3072, SA token probe returned non-timeout HTTP code.
  </done>
</task>

<task type="auto">
  <name>Task 2: IMPLEMENT — deploy systemd unit, wire .env, revert kb-api timeout (GO only)</name>
  <files>
    deploy/aliyun/systemd/omnigraph-vertex-proxy.service
  </files>
  <action>
**GATE: Only execute this task if Task 1 DECISION.md contains "SPIKE: GO".**

If DECISION.md says NO-GO, skip this task entirely and proceed to the output section.

---

**Step A: Write the systemd unit to the repo**

Create `deploy/aliyun/systemd/omnigraph-vertex-proxy.service` modeled after
`deploy/aliyun/systemd/omnigraph-mcp-tunnel.service` (same SSH flags, same Restart=always,
same BatchMode=yes) but with `-D 127.0.0.1:18080` instead of `-L`.

```ini
[Unit]
Description=OmniGraph SSH SOCKS5 egress proxy: Aliyun -> Hermes (Vertex/Google API unblock, TEMPORARY #75 mitigation)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
# -D opens SOCKS5 server on Aliyun loopback port 18080
# All Python processes with ALL_PROXY=socks5h://127.0.0.1:18080 route Google traffic via Hermes
# TEMPORARY: disable this service when IT fixes ACK NetworkPolicy for wg-gcp-sg
ExecStart=/usr/bin/ssh -N -T \
  -o ConnectTimeout=15 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new \
  -D 127.0.0.1:18080 \
  hermes
Restart=always
RestartSec=10
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
```

Note: uses `hermes` as SSH target (Aliyun ~/.ssh/config has the real host/port/user).
Do NOT write Hermes host/port/user into this file (CLAUDE.md Principle #5).

**Step B: Deploy the unit to Aliyun**

SCP the unit file to Aliyun (git fetch is 443-blocked on Aliyun, use SCP):
```
scp deploy/aliyun/systemd/omnigraph-vertex-proxy.service aliyun-vitaclaw:/etc/systemd/system/
```

Then on Aliyun:
```
ssh aliyun-vitaclaw 'systemctl daemon-reload && systemctl enable omnigraph-vertex-proxy.service && systemctl start omnigraph-vertex-proxy.service'
```

Wait 5 seconds, then verify it is active:
```
ssh aliyun-vitaclaw 'systemctl is-active omnigraph-vertex-proxy.service && ss -tlnp | grep 18080'
```
Expect: `active` AND `LISTEN 127.0.0.1:18080`.

**Step C: Add ALL_PROXY and NO_PROXY to /root/.hermes/.env on Aliyun**

First, backup .env:
```
ssh aliyun-vitaclaw 'cp /root/.hermes/.env /root/.hermes/.env.bak-pre-socks5-260630'
```

Then append the two proxy vars (ONLY if not already present):
```
ssh aliyun-vitaclaw 'grep -q "^ALL_PROXY=" /root/.hermes/.env || echo "ALL_PROXY=socks5h://127.0.0.1:18080" >> /root/.hermes/.env'
ssh aliyun-vitaclaw 'grep -q "^NO_PROXY=" /root/.hermes/.env || echo "NO_PROXY=api.deepseek.com,siliconflow.cn,openrouter.ai,localhost,127.0.0.1" >> /root/.hermes/.env'
```

Verify they are present:
```
ssh aliyun-vitaclaw 'grep -E "^(ALL_PROXY|NO_PROXY)=" /root/.hermes/.env'
```
Expected output:
```
ALL_PROXY=socks5h://127.0.0.1:18080
NO_PROXY=api.deepseek.com,siliconflow.cn,openrouter.ai,localhost,127.0.0.1
```

**Step D: Revert KB_SYNTHESIZE_TIMEOUT in kb-api override.conf**

The timeout was lowered from 240→30 as a #75 mitigation (backup: .bak-pre-timeout-260629).
Now that embedding should recover, revert it:
```
ssh aliyun-vitaclaw "sed -i 's/^Environment=\"KB_SYNTHESIZE_TIMEOUT=30\"/Environment=\"KB_SYNTHESIZE_TIMEOUT=240\"/' /etc/systemd/system/kb-api.service.d/override.conf"
```

Verify:
```
ssh aliyun-vitaclaw 'grep KB_SYNTHESIZE_TIMEOUT /etc/systemd/system/kb-api.service.d/override.conf'
```
Expected: `Environment="KB_SYNTHESIZE_TIMEOUT=240"` (NOT 30).

Then restart kb-api and daemon-reload:
```
ssh aliyun-vitaclaw 'systemctl daemon-reload && systemctl restart kb-api.service'
```
Wait 10 seconds, verify kb-api is healthy:
```
ssh aliyun-vitaclaw 'systemctl is-active kb-api.service && curl -s http://localhost:8766/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(\"KB_API OK\" if d.get(\"status\")==\"healthy\" else d)"'
```

**Step E: End-to-end smoke — real embedding call via the .env-loaded proxy**

This confirms the systemd-resident tunnel + .env vars work together (not just the nohup spike):
```
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
  set -a && source /root/.hermes/.env && set +a && \
  /root/OmniGraph-Vault/venv-aim1/bin/python -c "
import os, asyncio
from lib.lightrag_embedding import lightrag_embedding_func
async def smoke():
    result = await lightrag_embedding_func(['"'"'smoke test post-proxy-deploy'"'"'])
    print(f'"'"'EMBED OK dim={len(result[0])}'"'"' if result and len(result[0])>0 else '"'"'EMBED FAIL'"'"')
asyncio.run(smoke())
"'
```
Expected: `EMBED OK dim=3072`

Also verify DeepSeek is NOT routed through proxy (NO_PROXY working). The ingest cron
will handle this naturally — if DeepSeek works normally at next cron fire, proxy bypass is fine.
For now, a quick DNS-level check suffices:
```
ssh aliyun-vitaclaw 'set -a && source /root/.hermes/.env && set +a && python3 -c "import os; print(os.environ.get('"'"'ALL_PROXY'"'"','"'"'NOT SET'"'"'), os.environ.get('"'"'NO_PROXY'"'"','"'"'NOT SET'"'"'))"'
```

**Step F: Trigger one manual ingest to confirm pipeline flows**

```
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && \
  set -a && source /root/.hermes/.env && set +a && \
  /root/OmniGraph-Vault/venv-aim1/bin/python batch_ingest_from_spider.py \
  --max-articles 2 >> /tmp/proxy-smoke-ingest.log 2>&1 &'
```
Wait 120 seconds, then check the log tail:
```
ssh aliyun-vitaclaw 'tail -30 /tmp/proxy-smoke-ingest.log'
```
Look for: `Done — N candidates processed` (not `TransportError oauth2 ConnectTimeout`).
Note: 2 articles may take 4-8 minutes at current per-article wall time. If the 120s window
only shows "Starting batch..." without a ConnectTimeout error, that is a positive signal
(embedding workers are making progress). A full success confirmation will come with the
next scheduled cron fire.

**Step G: Commit the repo unit file**

On local repo (NOT Aliyun git):
```
git add deploy/aliyun/systemd/omnigraph-vertex-proxy.service
git commit -m "feat(260630-jgx): add omnigraph-vertex-proxy.service — SOCKS5 egress proxy via Hermes (#75 temp mitigation)"
```

**Step H: Update DECISION.md with IMPLEMENT result**

Append to DECISION.md:
- Timestamp of implementation
- omnigraph-vertex-proxy.service status on Aliyun (systemctl is-active)
- KB_SYNTHESIZE_TIMEOUT revert confirmed (240)
- Embedding smoke result (dim=3072 or failure)
- .env backup location (.env.bak-pre-socks5-260630)
- Rollback procedure (full text, so IT handoff is self-contained):
  ```
  ROLLBACK (when IT confirms ACK NetworkPolicy fix):
  1. Verify WireGuard recovery: ssh aliyun-vitaclaw 'wg show wg-gcp-sg | grep latest-handshake'
     → must show timestamp within last 30s
  2. Test direct Google egress: ssh aliyun-vitaclaw 'curl -sS -o /dev/null -w "%{http_code}\n" https://oauth2.googleapis.com/token'
     → expect 400 within 2s (not timeout)
  3. Remove proxy vars from /root/.hermes/.env:
     ssh aliyun-vitaclaw 'sed -i "/^ALL_PROXY=/d; /^NO_PROXY=/d" /root/.hermes/.env'
  4. Stop and disable the tunnel service:
     ssh aliyun-vitaclaw 'systemctl disable --now omnigraph-vertex-proxy.service'
  5. Restart ingest services so they pick up the clean env:
     ssh aliyun-vitaclaw 'systemctl restart omnigraph-daily-ingest.service'
  6. Verify: embedding smoke (as in Task 2 Step E) should still return dim=3072 via direct WG path
  ```
  </action>
  <verify>
    <automated>
      # Local: unit file exists in repo
      test -f "deploy/aliyun/systemd/omnigraph-vertex-proxy.service" && grep -q "socks5" deploy/aliyun/systemd/omnigraph-vertex-proxy.service && echo "UNIT FILE OK"

      # Remote checks (run via Bash tool with ssh aliyun-vitaclaw '...'):
      # systemctl is-active omnigraph-vertex-proxy.service → active
      # ss -tlnp | grep 18080 → LISTEN 127.0.0.1:18080
      # grep -E "^(ALL_PROXY|NO_PROXY)=" /root/.hermes/.env → both lines present
      # grep KB_SYNTHESIZE_TIMEOUT /etc/systemd/system/kb-api.service.d/override.conf → =240
      # systemctl is-active kb-api.service → active
    </automated>
  </verify>
  <done>
    omnigraph-vertex-proxy.service is active on Aliyun (LISTEN :18080).
    ALL_PROXY=socks5h://127.0.0.1:18080 and NO_PROXY present in /root/.hermes/.env.
    KB_SYNTHESIZE_TIMEOUT reverted to 240 and kb-api healthy.
    Embedding smoke returns dim=3072.
    Unit file committed to repo at deploy/aliyun/systemd/omnigraph-vertex-proxy.service.
    DECISION.md records the full rollback procedure for IT handoff.
  </done>
</task>

</tasks>

<verification>
## Phase-level checks

### If SPIKE NO-GO:
- DECISION.md exists with NO-GO + exact failure reason
- No lingering tunnel processes: `ssh aliyun-vitaclaw 'ss -tlnp | grep 18080'` → empty
- No /etc/hosts changes that weren't intentional (Google pins removed = expected; nothing else changed)
- No .env modifications (vars NOT added)
- No systemd units deployed on Aliyun
- KB_SYNTHESIZE_TIMEOUT still at 30 (unchanged, will need manual revert when IT fixes ACK)

### If SPIKE GO + IMPLEMENT complete:
- `ssh aliyun-vitaclaw 'systemctl is-active omnigraph-vertex-proxy.service'` → `active`
- `ssh aliyun-vitaclaw 'ss -tlnp | grep 18080'` → `LISTEN 127.0.0.1:18080`
- `ssh aliyun-vitaclaw 'grep -E "^ALL_PROXY=" /root/.hermes/.env'` → `ALL_PROXY=socks5h://127.0.0.1:18080`
- `ssh aliyun-vitaclaw 'grep -E "^NO_PROXY=" /root/.hermes/.env'` → includes deepseek + siliconflow
- `ssh aliyun-vitaclaw 'grep KB_SYNTHESIZE_TIMEOUT /etc/systemd/system/kb-api.service.d/override.conf'` → `=240`
- `ssh aliyun-vitaclaw 'systemctl is-active kb-api.service'` → `active`
- Embedding smoke returns dim=3072 (not timeout)
- `test -f deploy/aliyun/systemd/omnigraph-vertex-proxy.service` → file exists in local repo
- Git log shows commit for the unit file
</verification>

<success_criteria>
SPIKE phase (mandatory):
- [ ] httpx[socks] installed on Aliyun venv-aim1 (socksio present)
- [ ] /etc/hosts Google pins removed (or confirmed absent)
- [ ] Temporary tunnel opened, port 18080 bound on Aliyun loopback
- [ ] SA token refresh curl probe: non-timeout HTTP response via socks5h
- [ ] Python embedding probe: EMBED OK dim=3072
- [ ] Temporary tunnel killed (port 18080 unbound after spike)
- [ ] DECISION.md written with SPIKE result (GO or NO-GO)

IMPLEMENT phase (only if GO):
- [ ] deploy/aliyun/systemd/omnigraph-vertex-proxy.service written to repo
- [ ] Unit deployed to /etc/systemd/system/ on Aliyun via SCP
- [ ] systemctl enable + start successful; service active
- [ ] ALL_PROXY + NO_PROXY appended to /root/.hermes/.env (with backup)
- [ ] KB_SYNTHESIZE_TIMEOUT reverted 30→240 in kb-api override.conf
- [ ] kb-api restarted and healthy (/health 200)
- [ ] End-to-end embedding smoke returns dim=3072 with .env-loaded proxy
- [ ] Unit file committed to repo with explicit git add
- [ ] DECISION.md updated with rollback procedure
</success_criteria>

<output>
After completion, create `.planning/quick/260630-jgx-260630-hermes-vertex-egress-proxy/260630-jgx-SUMMARY.md`

Include:
- SPIKE result (GO / NO-GO)
- If GO: service status, embedding dim confirmed, KB_SYNTHESIZE_TIMEOUT reverted, commit hash
- If NO-GO: exact failure reason, Aliyun state confirmed clean
- Newly surfaced issues (if any) for orchestrator to add to ISSUES.md
- #75 status update: "B-mitigation DEPLOYED (proxy active, embedding recovering)" or "B-mitigation FAILED (spike NO-GO)"
</output>
