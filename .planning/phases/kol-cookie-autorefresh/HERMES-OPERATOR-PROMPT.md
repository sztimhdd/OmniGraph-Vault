# Hermes Operator Prompt — kol-cookie-autorefresh Wave 3

> **⚠️ These are Hermes-WRITE operator-channel steps.** Hermes was RO-frozen until **2026-06-22**.
> The user has authorized these writes for this session. If running unattended/later, execute on or
> after 2026-06-22. The orchestrator does NOT ssh-write Hermes directly (Principle #5) — these steps
> are run by the operator (you) on the Hermes machine.
>
> **Connection:** `ssh -p 49221 sztimhdd@ohca.ddns.net` (host OH-Desktop, WSL2). Repo: `~/OmniGraph-Vault`.
> Env file: `~/.hermes/.env`. The wrapper uses **system python3 + websocket-client** (NOT the venv).

Five steps (A–D required; E optional). Each has a command and an expected result. Run them on Hermes.

---

## STEP A — Sync the wrapper to Hermes

The refresh wrapper (`scripts/refresh_wechat_cookie.py` + `scripts/lib/cdp_client.py`) is committed to
`origin/main` (commits `c71d148`/`6ebbf0d`/`692f18b`). Pull it onto Hermes:

```bash
cd ~/OmniGraph-Vault
git pull --ff-only origin main
# Confirm the files landed:
ls -la scripts/refresh_wechat_cookie.py scripts/lib/cdp_client.py
```
Expected: both files present.

Ensure system python3 has websocket-client (the wrapper needs it; the venv is NOT used at runtime):
```bash
python3 -c "import websocket; print('ws ok')" || pip install --user websocket-client
```
Expected: `ws ok` (or a successful install then `ws ok`).

Smoke the wrapper imports + CLI without touching anything (`--dry-run` does A/B/C detect + prints the
would-be writeback, never writes Aliyun):
```bash
cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --help
```
Expected: argparse help prints (proves the pinned `from lib.cdp_client import ...` resolves from repo root). No `ImportError`/`ModuleNotFoundError`.

---

## STEP B — Add the rotated WeChat creds to ~/.hermes/.env  (KCA-8 / ISSUES #58)

**FIRST: rotate the WeChat account password.** The OLD password was committed in the public repo
(now redacted, but the history exposure stands). Log into the WeChat MP account and set a NEW password.

Then append the rotated creds to `~/.hermes/.env` (the wrapper reads `WECHAT_MP_ACCOUNT` /
`WECHAT_MP_PASSWORD` from the environment for the B-level account-login fallback):

```bash
# Replace the placeholders with the REAL rotated values. Do NOT paste them into chat / any repo file.
printf 'WECHAT_MP_ACCOUNT=%s\n' '<rotated-account-id>'   >> ~/.hermes/.env
printf 'WECHAT_MP_PASSWORD=%s\n' '<rotated-password>'    >> ~/.hermes/.env
# Verify count WITHOUT echoing values:
grep -c '^WECHAT_MP_' ~/.hermes/.env
```
Expected: `2`.

Also update the **Edge saved password** in the `C:\Edge-Auto-Profile` profile to the rotated password,
so the B-level browser-saved-login path stays consistent (open Edge with that profile → wechat MP login →
save the new password).

---

## STEP C — Repoint the stale Hermes ssh alias  (KCA-4 writeback target)

Hermes's `~/.ssh/config` alias `vitaclaw-aliyun` still points at the DEAD old IP `101.133.154.49`.
The wrapper's writeback (`writeback_to_aliyun`) scp/ssh-es to this alias. Repoint it to the new EIP:

```bash
cp ~/.ssh/config ~/.ssh/config.bak-pre-kca
# Change the vitaclaw-aliyun HostName from 101.133.154.49 to 47.117.244.253 (keep Port/User/IdentityFile):
sed -i 's/101\.133\.154\.49/47.117.244.253/' ~/.ssh/config
# Verify it resolves to the live Aliyun box:
ssh -o ConnectTimeout=15 vitaclaw-aliyun "hostname"
```
Expected: `iZj1imk39yc55iZ` (the rebuilt Aliyun box).

> If the alias stanza differs or sed misses, edit `~/.ssh/config` by hand: the `Host vitaclaw-aliyun`
> block's `HostName` must read `47.117.244.253`.

---

## STEP D — Probe `hermes send --image` capability  (level-C QR delivery)

The wrapper's level-C QR path sends the QR png to Telegram via `hermes send --image` **if supported**,
else falls back to text + the `/tmp/wx_qr_code.png` path. Record which:

```bash
hermes send --help 2>&1 | grep -iE 'image|photo|attach' || echo "NO --image flag"
```
If a flag exists, confirm it actually delivers (send a tiny test image to yourself):
```bash
# only if --image / --photo / --attach exists:
hermes send -t telegram --image /tmp/test.png "kca capability probe"   # adjust flag name to what --help showed
```
Expected: either a confirmed image lands in your Telegram chat (capability = **supported**), or you
record **not-supported** (the wrapper degrades to text + path gracefully — no action needed).

**Record the result (supported / not-supported)** — report it back so Plan 05 picks the right branch.

---

## STEP E (optional) — Autostart the headed CDP Edge

There is currently NO autostart for the `:9222` headed Edge that holds the logged-in WeChat session.
The wrapper self-heals it (relaunches via PowerShell if `:9222` is down), so this is optional — but a
Windows Task Scheduler entry that launches Edge on logon reduces the self-heal dependency:

```
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --remote-allow-origins=* --user-data-dir=C:\Edge-Auto-Profile --no-sandbox
```
(Task Scheduler → Create Task → Trigger: At log on → Action: the line above. Optional.)

---

## When done — report back

Tell the orchestrator:
1. **EXECUTED** (steps A–D done) or **DEFERRED** (to post-2026-06-22) — Plan 05 branches on this.
2. The **STEP D result**: is `hermes send --image` supported? (yes / no)
3. Any step that failed + its output.

Quick confirm bundle (run on Hermes, paste the output):
```bash
echo "wrapper: $(ls ~/OmniGraph-Vault/scripts/refresh_wechat_cookie.py 2>/dev/null && echo present || echo MISSING)"
echo "env creds: $(grep -c '^WECHAT_MP_' ~/.hermes/.env)"
echo "alias: $(ssh -o ConnectTimeout=15 vitaclaw-aliyun hostname 2>&1)"
echo "dry-run import: $(cd ~/OmniGraph-Vault && python3 scripts/refresh_wechat_cookie.py --help >/dev/null 2>&1 && echo ok || echo FAIL)"
```
Expected: `present` / `2` / `iZj1imk39yc55iZ` / `ok`.
