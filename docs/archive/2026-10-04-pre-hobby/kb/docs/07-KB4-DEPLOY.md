# KB-4: 部署+上线 (1天)

## Goal
Deploy to Aliyun ECS (Hermes), configure Caddy, set up cron for daily rebuild, verify live.

## Steps
1. SCP/rsync kb/ projects to Hermes:
   - `kb/output/` — static HTML
   - `kb_api.py` — FastAPI
2. Install dependencies: fastapi, uvicorn, lightrag
3. Set up systemd service:
   ```
   [Unit]
   Description=Knowledge Base FastAPI
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/vitaclaw/kb
   Environment=PYTHONPATH=/opt/vitaclaw/OmniGraph-Vault
   ExecStart=/usr/bin/uvicorn kb_api:app --host 127.0.0.1 --port 8766
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
4. Update Caddy config:
   ```
   ohca.ddns.net {
       reverse_proxy /static/img/* localhost:8766
       reverse_proxy /kb/* localhost:8766
       reverse_proxy /* localhost:3001
   }
   ```
5. Set up daily cron:
   ```
   0 12 * * * cd /opt/vitaclaw/kb && python export_knowledge_base.py && systemctl reload caddy
   ```
6. Verify:
   - curl http://localhost:8766/articles
   - curl http://localhost:8766/article/{known_hash}
   - Browser open https://ohca.ddns.net/kb/
7. Retire old image server: `kill $(pgrep -f "http.server 8765")`

## Rollback
- Caddy config revert to previous version
- systemctl stop kb-api → restart caddy
- python -m http.server 8765 --directory ~/.hermes/omonigraph-vault/images &
