# 260610-eoy — Secrets Inventory (paths + key names ONLY, NO values)

**Goal:** verify-able checklist. After restore, confirm each secret path exists with non-zero size and that the listed env-var names appear when grepped (without revealing values).

**⚠️ This file is committed to git. NO VALUES allowed.**

---

## Hermes / OmniGraph layer

### `/root/.hermes/.env` — 2687 bytes (production)

Variables defined (no values):

```
APIFY_TOKEN
APIFY_TOKEN_BACKUP
AUXILIARY_VISION_MODEL
BRAVE_API_KEY
BRAVE_SEARCH_API_KEY
CDP_URL
DEEPSEEK_API_KEY
EMBEDDING_MODEL
FIRECRAWL_API_KEY
GATEWAY_ALLOW_ALL_USERS
GEMINI_API_KEY
GEMINI_API_KEY_BACKUP
GEMINI_BACKUP_KEY
GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CLOUD_LOCATION
GOOGLE_CLOUD_PROJECT
GOOGLE_GENAI_USE_VERTEXAI
HERMES_CRON_TIMEOUT
HERMES_MAX_ITERATIONS
HINDSIGHT_API_KEY
HINDSIGHT_LLM_API_KEY
LIGHTRAG_EMBEDDING_TIMEOUT
LIGHTRAG_LLM_TIMEOUT
OMNIGRAPH_EMBEDDING_KEYS
OMNIGRAPH_GEMINI_KEY
OMNIGRAPH_PROCESSED_BACKOFF
OMNIGRAPH_VECTOR_STORAGE
OMNIGRAPH_VERTEX_SA_JSON_PATH
OMNIGRAPH_VISION_SKIP_BALANCE_CHECK
OMNIGRAPH_VISION_SKIP_PROVIDERS
OPENROUTER_API_KEY
QDRANT_URL
RAILWAY_TOKEN
SILICONFLOW_API_KEY
TAVILY_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
TERMINAL_MAX_FOREGROUND_TIMEOUT
WEIXIN_ACCOUNT_ID
WEIXIN_ALLOW_ALL_USERS
WEIXIN_ALLOWED_USERS
WEIXIN_BASE_URL
WEIXIN_CDN_BASE_URL
WEIXIN_DM_POLICY
WEIXIN_GROUP_ALLOWED_USERS
WEIXIN_GROUP_POLICY
WEIXIN_HOME_CHANNEL
WEIXIN_TOKEN
```

**Critical:** APIFY_TOKEN, GEMINI_API_KEY (×3), DEEPSEEK_API_KEY, OPENROUTER_API_KEY, SILICONFLOW_API_KEY, OMNIGRAPH_GEMINI_KEY, OMNIGRAPH_EMBEDDING_KEYS, WEIXIN_TOKEN.
**Re-acquire from:** Apify dashboard / Google Cloud Console / DeepSeek dashboard / OpenRouter / SiliconFlow / WeChat MP. Some keys (WeChat) are session-bound and require re-login.

### `/root/.hermes/gcp-paid-sa.json` — 2400 bytes

Vertex AI service account key. Rotate every ≤ 90d.
**Re-issue from:** Google Cloud Console → IAM → Service Accounts → Keys → Create new.

### `/root/.hermes/auth.json` — 1246 bytes

Hermes gateway auth state.
**Re-acquire:** unknown — likely interactive login on first run if missing.

### `/root/.hermes/config.yaml` — 60 bytes

Hermes config (small, structural).

---

## SSH / Infrastructure

### `/root/.ssh/`

```
id_ed25519                      411 bytes  — private key (Hermes ↔ Aliyun)
id_ed25519.pub                  101 bytes  — corresponding public key
authorized_keys                 550 bytes  — incoming SSH keys (laptop + others)
authorized_keys.bak-pre-aim4-1-20260525-073631  441 bytes  — backup, optional
known_hosts                     978 bytes  — peer fingerprints
known_hosts.old                 142 bytes  — older fingerprints
```

---

## Vitaclaw SaaS layer

### `/opt/vitaclaw/planb-local-m1/.env` — 311 bytes

Tenant routing config:

```
TENANT_A_APP_PORT
TENANT_A_POSTGRES_HOST_PORT
TENANT_A_QDRANT_PREFIX
TENANT_A_SCHEMA
TENANT_B_APP_PORT
TENANT_B_POSTGRES_HOST_PORT
TENANT_B_QDRANT_PREFIX
TENANT_B_SCHEMA
TRIAL_SELECT_ROUTE
```

No external secrets — just port + schema mapping.

### `/opt/vitaclaw/planb-local-m1/.env.local` — 53 bytes

```
DEEPSEEK_API_KEY
```

### `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env` — 3521 bytes

Production tenant secrets — **largest secret bundle in the project**.

```
ADMIN_EMAILS
AGENT_MODE
APP_PORT
APP_URL
COMPOSE_FILE
COMPOSE_PROJECT_NAME
CORS_ORIGIN
DATABASE_URL
DATA_ROOT
DB_ROOT
HOST
IDENTITY_HOST_PORT
INTERNAL_SERVICE_TOKEN
JWT_AUDIENCE
JWT_ISSUER
JWT_KEY_ID
JWT_PRIVATE_KEY
JWT_PUBLIC_KEY
LLM_BASE_URL
LLM_MODEL
LLM_PROVIDER
LOCAL_RUNTIME_ROOT
LOG_ROOT
MEMORY_FILES_BASE_PATH
MODEL_PROVIDER_API_KEY
PORT
POSTGRES_DB
POSTGRES_HOST_PORT
POSTGRES_PASSWORD
POSTGRES_USER
PUBLIC_REGISTRATION_ENABLED
QDRANT_COLLECTION_PREFIX
TENANT_SCHEMA
TENANT_SLUG
UPSTREAM_REPO_ROOT
UPSTREAM_SKILL_REPO_ROOT
UPSTREAM_WEB_REPO_ROOT
WORKSPACE_FILES_BASE_PATH
```

**Critical:** JWT_PRIVATE_KEY, JWT_PUBLIC_KEY, POSTGRES_PASSWORD, INTERNAL_SERVICE_TOKEN, MODEL_PROVIDER_API_KEY, DATABASE_URL.
**Cannot easily re-issue:** JWT keypair must match what tenant clients have (or rotate everything in lockstep). POSTGRES_PASSWORD must match what's actually in the dumped postgres data.

### `/opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed` — 87 bytes

Seed for first-boot. Tiny.

### `/etc/vitaclaw/vitaclaw-site.env` — 83 bytes

```
DEEPSEEK_API_KEY
NODE_ENV
PORT
```

Plus 2 historical .bak files (72 + 83 bytes).

---

## Verification checklist (post-restore)

After running RESTORE_RUNBOOK Step 2 (decrypt + place secrets):

```bash
# 1. Verify all expected paths exist with non-zero size
for f in \
  /root/.hermes/.env \
  /root/.hermes/auth.json \
  /root/.hermes/gcp-paid-sa.json \
  /root/.hermes/config.yaml \
  /root/.ssh/id_ed25519 \
  /root/.ssh/id_ed25519.pub \
  /root/.ssh/authorized_keys \
  /root/.ssh/known_hosts \
  /opt/vitaclaw/planb-local-m1/.env \
  /opt/vitaclaw/planb-local-m1/.env.local \
  /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env \
  /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env.seed \
  /etc/vitaclaw/vitaclaw-site.env; do
  if [ -s "$f" ]; then
    echo "OK $(stat -c '%s' "$f") bytes  $f"
  else
    echo "MISSING/EMPTY                  $f"
  fi
done

# 2. Verify each .env has the expected key NAMES (no value leak)
for f in /root/.hermes/.env \
         /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env; do
  echo "=== $f keys ==="
  grep -E '^[A-Z_][A-Z0-9_]*=' "$f" | cut -d= -f1 | sort -u
done

# 3. Sanity check critical sizes
[ "$(stat -c '%s' /root/.hermes/.env)" -ge 2500 ] && echo "OK hermes .env" || echo "WRONG hermes .env"
[ "$(stat -c '%s' /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env)" -ge 3000 ] && echo "OK tenantB .env" || echo "WRONG tenantB .env"
[ "$(stat -c '%s' /root/.hermes/gcp-paid-sa.json)" -ge 2000 ] && echo "OK SA json" || echo "WRONG SA json"

# 4. Verify perms (NEVER world-readable)
stat -c '%a %n' \
  /root/.hermes/.env \
  /root/.hermes/gcp-paid-sa.json \
  /root/.ssh/id_ed25519 \
  /etc/vitaclaw/vitaclaw-site.env \
  /opt/vitaclaw/planb-local-m1/vitaclaw-local/tenants/tenantB/.env
# Expected: 600 / 600 / 600 / 640 / 600
```

---

## Rotation recommendations (post-restore stabilization)

| Secret | Why rotate | When |
|---|---|---|
| Aliyun SSH password (memory note: `Hzyc@#0507` was in chat history) | High-value root password leaked through prior chat sessions | Within 7 days of cutover |
| `gcp-paid-sa.json` | Standard 90-day SA key rotation hygiene | Within 90 days of last rotation |
| All `*_API_KEY` (Apify, Gemini, DeepSeek, OpenRouter, SiliconFlow) | Backup keys exist (`*_BACKUP`) — rotate primary, keep backup as fallback | Annually OR on suspected breach |
| `JWT_PRIVATE_KEY` | Tenant JWT signing — coordinate with all tenant clients | Annually |
| `POSTGRES_PASSWORD` | Coordinate with pg_dump restored content; require app restart | When changing infra |

**No rotation required for:** structural envs (PORT, NODE_ENV, COMPOSE_PROJECT_NAME, etc).
