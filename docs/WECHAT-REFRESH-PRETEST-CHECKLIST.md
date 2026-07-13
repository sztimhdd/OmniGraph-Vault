# WeChat Cookie Refresh — Pre-Test Checklist

**Purpose:** Ensure WeChat session is valid before running E2E health tests. Session expiry (ret=200003) is the most common blocker.

**When to use:** Before each E2E test run.

---

## Quick Status Check

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Check current session validity with a single-article scan
python3 batch_scan_kol.py --max-accounts 1 --max-articles 1

# Look at the output:
# - If ret=0 and article discovered → session OK, proceed to E2E test
# - If ret=200003 and "invalid session" → session expired, follow refresh steps below
EOF
```

---

## Session Expired (ret=200003) — Manual Recovery

When WeChat session is expired:

### Step 1: Login on Hermes Edge Browser

1. **SSH to Hermes PC** or go directly to the machine
2. **Open Edge browser** on Hermes
3. Navigate to `https://mp.weixin.qq.com`
4. Scan the QR code with your phone's WeChat
5. Confirm login on your phone
6. Wait for Edge to load the dashboard (session saved to Hermes)

### Step 2: Verify Session Restored

```bash
ssh aliyun-vitaclaw << 'EOF'
# Hermes-based refresh (primary, requires Hermes Edge CDP online)
cd /root/OmniGraph-Vault
python3 scripts/refresh_wechat_cookie.py

# OR manually test if you already renewed the session
python3 batch_scan_kol.py --max-accounts 1 --max-articles 1

# Expected: ret=0, article discovered
EOF
```

### Step 3: If Hermes Unavailable (Mac Fallback)

If Hermes PC is offline or CDP unreachable:

1. **On your Mac**, manually start Chrome with remote debugging:
   ```bash
   open -a "Google Chrome" --args --remote-debugging-port=9222
   ```

2. **On Aliyun**, set fallback and retry:
   ```bash
   ssh aliyun-vitaclaw << 'EOF'
   export CDP_URL=http://YOUR_MAC_LOCAL_IP:9222
   cd /root/OmniGraph-Vault
   python3 scripts/refresh_wechat_cookie.py
   EOF
   ```

### Step 4: Verify Session Persisted to Aliyun

After successful login on Hermes Edge:

```bash
ssh aliyun-vitaclaw << 'EOF'
cd /root/OmniGraph-Vault

# Test if the new session is now visible to Aliyun
python3 batch_scan_kol.py --max-accounts 1 --max-articles 1

# Expected: ret=0, articles discovered
# If still ret=200003, the session didn't transfer; try Step 3 (Mac fallback)
EOF
```

---

## Preventive Maintenance

WeChat sessions typically expire after **7–14 days** of inactivity. The proactive refresh runs automatically:

```bash
ssh aliyun-vitaclaw "systemctl list-timers omnigraph-kol-refresh.timer"
```

**Schedule:** Fires 5 minutes before daily scan (default: 06:00 UTC → 13:00 CST).

If refresh fails, Telegram alert is sent; next scan will detect expired session and notify you.

---

## Pre-Test Checklist

Before running `./e2e_health_test.sh --quick` or `--full`:

```bash
# ✅ Session Status
ssh aliyun-vitaclaw "python3 /root/OmniGraph-Vault/batch_scan_kol.py --max-accounts 1 --max-articles 1 | grep -E 'ret=|ok,' "

# ✅ Disk Space (>5% free on /)
ssh aliyun-vitaclaw "df / | tail -1 | awk '{print \$5}'"

# ✅ Dependencies
ssh aliyun-vitaclaw "python3 -c \"from lib.models import INGESTION_LLM, EMBEDDING_MODEL; print(f'LLM: {INGESTION_LLM}, Embed: {EMBEDDING_MODEL}')\""

# ✅ Database
ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db 'SELECT COUNT(*) FROM ingestions'"

# ✅ graphml
ssh aliyun-vitaclaw "ls -lh /root/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml"
```

If all four checks pass → proceed to E2E test.

---

## Troubleshooting

| Issue | Diagnostic | Fix |
|-------|-----------|-----|
| ret=200003 (invalid session) | WeChat API rejects auth | Manual QR login or Step 2–3 above |
| ret=200004 (not official account) | Wrong account selected | Check kol_config.py FAKEIDS |
| ret=301 (frequency limit) | Too many scan requests | Wait 1 hour, retry |
| ret=500 (API error) | WeChat backend issue | Retry after 5 min |
| Connection refused (Hermes) | Hermes PC offline or firewall | Use Mac fallback (Step 3) |

---

## Next Step

Once session is confirmed valid:

```bash
./scripts/e2e_health_test.sh --quick   # 10 min quick run
./scripts/e2e_health_test.sh --full    # 20–30 min full run
```

Both will reference `docs/E2E-HEALTH-TEST.md` for detailed step-by-step procedures.
