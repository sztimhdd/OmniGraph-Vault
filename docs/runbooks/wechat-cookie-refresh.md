# WeChat Cookie Refresh Runbook

## Overview

When the WeChat MP API session (TOKEN + COOKIE) expires, all KOL account scans
return `ret=200003` ("invalid session"). Sessions last 14-31 days.

**Last Updated:** 2026-07-11  
**Current source machine:** Mac (Brave CDP :9222) — replaced WSL/Windows Edge  
**Canonical skill:** `skills/wechat-cdp-credential-refresh/SKILL.md`

---

## 1. Detection

Any of these symptoms indicate session expiry:

- `ret=200003` in scan logs: `journalctl -u omnigraph-kol-scan-batch@1.service -n 50`
- `WECHAT_SESSION_INVALID: N/total` in batch output (>= 30% threshold)
- Daily digest shows 0 new articles for 2+ consecutive days
- Manual API test returns non-zero ret:

```bash
ssh aliyun "cd /root/OmniGraph-Vault && python -c '
from kol_config import COOKIE,TOKEN
import requests
r=requests.get(\"https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&type=9&count=1&begin=0&f=json&ajax=1&token=\"+TOKEN,headers={\"Cookie\":COOKIE},timeout=10)
print(r.json().get(\"base_resp\",{}))'"
# Expected: {"ret": 0, ...} — if ret != 0, session is stale
```

---

## 2. Mac CDP Refresh Procedure (current method)

### 2.1 Check Existing Tabs

```bash
curl -s http://127.0.0.1:9222/json | python3 -c "
import sys,json
for p in json.load(sys.stdin):
  if 'mp.weixin.qq.com/cgi-bin/home' in p.get('url',''):
    print('FOUND logged-in tab')
    print('URL:', p['url'][:120])
    print('Title:', p['title'])
"
```

The logged-in tab URL contains `token=NNNNNNNNN` — this is the new TOKEN.

### 2.2 Extract Token + Cookies

```python
import requests, json, websocket

CDP = 'http://127.0.0.1:9222'
pages = requests.get(CDP + '/json').json()

for p in pages:
    if 'mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=' in p.get('url',''):
        # Extract token from URL
        import re
        token = re.search(r'token=(\d+)', p['url']).group(1)
        print(f'TOKEN = "{token}"')

        # Extract cookies via CDP WebSocket
        ws = websocket.create_connection(p['webSocketDebuggerUrl'])
        ws.send(json.dumps({'id':1,'method':'Page.enable'}))
        ws.recv()
        ws.send(json.dumps({'id':2,'method':'Network.getCookies'}))
        resp = json.loads(ws.recv())
        cookies = resp['result']['cookies']
        ws.close()

        cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in cookies)
        print(f'COOKIE = "{cookie_str}"')
        break
```

**Warning:** Never create new tabs via `PUT /json/new` — triggers WeChat re-auth redirect. Always use existing logged-in tabs.

### 2.3 Verify Page is Actually Logged In

```python
ws.send(json.dumps({'id':3,'method':'Runtime.evaluate',
    'params':{'expression':'document.body.innerText.substring(0,100)','returnByValue':True}}))
```

Expected: shows "首页 内容管理 互动管理..." — NOT "请重新登录".

### 2.4 Deploy to Aliyun

```bash
# Merge new TOKEN+COOKIE with existing FAKEIDS
ssh aliyun "python3 -c \"
old=open('/root/OmniGraph-Vault/kol_config.py').read()
# Extract FAKEIDS from old config
import re
m=re.search(r'FAKEIDS\s*=\s*\{', old)
start=m.start()
depth=0; end=start
for i,c in enumerate(old[start:],start):
    if c=='{': depth+=1
    elif c=='}':
        depth-=1
        if depth==0: end=i+1; break
fids_block=old[start:end]

# Build merged config
merged='''# kol_config.py — LOCAL ONLY, never commit

TOKEN = \\\"$TOKEN\\\"
COOKIE = \\\"$COOKIE\\\"

''' + fids_block
open('/root/OmniGraph-Vault/kol_config.py','w').write(merged)
print('Updated OK')
\""

# Restart scan services
ssh aliyun "systemctl restart omnigraph-kol-scan-batch@{1..4}.service"
```

---

## 3. Verification

```bash
# Quick API test
ssh aliyun "cd /root/OmniGraph-Vault && python -c '
from kol_config import COOKIE,TOKEN
import requests
r=requests.get(\"https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&type=9&count=1&begin=0&f=json&ajax=1&token=\"+TOKEN,headers={\"Cookie\":COOKIE},timeout=10)
print(r.json().get(\"base_resp\",{}))'"
# Expected: {ret: 0, err_msg: ok}

# Check scan health (30s after restart)
ssh aliyun "journalctl -u omnigraph-kol-scan-batch@1.service --since '1 min ago' -n 10 | grep -E 'ok|failed|WECHAT_SESSION_INVALID'"
# Expected: lines showing 'ok' accounts, zero WECHAT_SESSION_INVALID
```

---

## 4. Hard Constraints

- **Never create new CDP tabs** — use existing logged-in tabs only
- **Never paste cookie/token values** into chat, commits, or prompts
- **Always use `Network.getCookies`** — `document.cookie` misses HttpOnly cookies (slave_sid, data_ticket)
- **Preserve FAKEIDS** when updating — T+COOKIE change, FAKEIDS stay
- **kol_config.py is gitignored** — never commit, transfer via SCP only
- **Session lasts 14-31 days** — plan for monthly refresh

## See Also

- `skills/wechat-cdp-credential-refresh/SKILL.md` — full CDP procedure + edge cases
- `docs/HANDOFF-2026-07-11.md` — complete handoff for next agent
- `deploy/aliyun/systemd/omnigraph-kol-scan-alert.service` — B2 OnFailure handler
