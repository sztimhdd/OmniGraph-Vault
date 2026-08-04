#!/bin/bash
# patch_lightrag_entity_name.sh
# Fix LightRAG entity_name KeyError in operate.py (venv site-packages monkey-patch).
# H3 — Ponytail audit 2026-08-04: code-ify the manually applied patch.
#
# Idempotent: safe to run repeatedly (detects already-patched state).
# Before applying: asserts old pattern exists (correct file + line).
# After applying: asserts new pattern exists + runs data integrity query.

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────
# Auto-detect LightRAG operate.py in the active venv
VENV_DIR="${VENV_DIR:-/root/OmniGraph-Vault/venv-aim1}"
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || \
  find "$VENV_DIR" -type d -name site-packages -path "*/lib/*" | head -1)

if [ -z "$SITE_PACKAGES" ]; then
  echo "ERROR: cannot locate site-packages in $VENV_DIR"
  exit 1
fi

OPERATE_PY="$SITE_PACKAGES/lightrag/operate.py"

if [ ! -f "$OPERATE_PY" ]; then
  echo "ERROR: $OPERATE_PY not found. Is lightrag installed?"
  exit 1
fi

OLD_PATTERN='node_ids = [r\["entity_name"\] for r in results]'
NEW_PATTERN='node_ids = [r.get("entity_name", r.get("__id__", str(i))) for i, r in enumerate(results)]'

# ── Check already patched ─────────────────────────────────────────
if grep -qF 'r.get("entity_name"' "$OPERATE_PY"; then
  echo "✓ Already patched: $OPERATE_PY"
  # Still run verification
else
  # ── Pre-flight assertion ─────────────────────────────────────────
  if ! grep -qF 'node_ids = [r["entity_name"] for r in results]' "$OPERATE_PY"; then
    echo "ERROR: expected pattern not found in $OPERATE_PY."
    echo "LightRAG version may have changed. Manual review required."
    echo "Showing context around 'entity_name':"
    grep -n "entity_name" "$OPERATE_PY" | head -10
    exit 1
  fi

  echo "Pattern found. Patching..."

  # ── Backup ───────────────────────────────────────────────────────
  cp "$OPERATE_PY" "$OPERATE_PY.bak.$(date +%Y%m%d-%H%M%S)"
  echo "Backup: $OPERATE_PY.bak.$(date +%Y%m%d-%H%M%S)"

  # ── Apply patch ──────────────────────────────────────────────────
  sed -i "s/node_ids = \[r\[\"entity_name\"\] for r in results\]/node_ids = [r.get(\"entity_name\", r.get(\"__id__\", str(i))) for i, r in enumerate(results)]/" "$OPERATE_PY"

  # ── Post-patch assertion ─────────────────────────────────────────
  if ! grep -qF 'r.get("entity_name"' "$OPERATE_PY"; then
    echo "ERROR: patch failed — new pattern not found after sed."
    echo "Restoring from backup..."
    cp "$OPERATE_PY.bak.$(date +%Y%m%d-%H%M%S)" "$OPERATE_PY"
    exit 1
  fi

  echo "✓ Patch applied successfully to $OPERATE_PY"
fi

# ── Data integrity verification ────────────────────────────────────
echo ""
echo "=== Data integrity check ==="

python3 << 'PYEOF'
import sys, os
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6333")

try:
    from qdrant_client import QdrantClient
    c = QdrantClient("http://127.0.0.1:6333", timeout=10)
    
    # Check all three collections
    for coll_suffix in ["entities", "chunks", "relationships"]:
        coll = f"lightrag_vdb_{coll_suffix}_bge_m3_1024d"
        try:
            pts, _ = c.scroll(coll, limit=500, with_vectors=False)
            if coll_suffix == "entities":
                missing = [p.id for p in pts if "entity_name" not in (p.payload or {})]
                total = len(pts)
                pct = len(missing) / total * 100 if total else 0
                status = "✓" if pct < 5 else "⚠"
                print(f"{status} {coll}: {len(missing)}/{total} missing entity_name ({pct:.1f}%)")
                if pct >= 5:
                    print(f"  WARNING: high entity_name missing rate. KG queries may fail.")
                    sys.exit(2)
            else:
                print(f"  {coll}: {len(pts)} points scanned")
        except Exception as e:
            print(f"✗ {coll}: ERROR — {e}")
            sys.exit(1)
    
    print("✓ Data integrity check passed")
except ImportError:
    print("⚠ qdrant_client not installed — skipping data integrity check")
    print("  Install: pip install qdrant-client")
except Exception as e:
    print(f"⚠ Qdrant unreachable — skipping data integrity check: {e}")
PYEOF

echo ""
echo "=== Done ==="
echo "Restart kb-api and MCP to pick up the patch:"
echo "  systemctl restart omni-kb-api omni-mcp"
