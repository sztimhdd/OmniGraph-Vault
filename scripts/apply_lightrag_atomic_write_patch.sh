#!/usr/bin/env bash
# ISSUES #47: wire the LightRAG atomic-write monkey-patch into both Aliyun
# venvs via a .pth file, so it survives `pip install --force-reinstall lightrag`
# (which would otherwise revert the in-place vendored edit from 260608-e8l and
# re-open the 6/7 graphml-truncation corruption class).
#
# WHY .pth NOT sitecustomize.py — 2026-06-11 real-deploy test on Aliyun caught
# the sitecustomize approach SILENTLY FAILING: Debian ships its own
# /usr/lib/python3.11/sitecustomize.py (the apport exception hook), which sits
# at sys.path index 2, BEFORE the venv site-packages at index 4. CPython imports
# only the FIRST `sitecustomize` module on sys.path, so the venv-local one never
# loaded and the patch never fired at startup (verified: patch_flag=False on a
# bare interpreter). A .pth file has no such collision — the site module
# processes EVERY *.pth in site-packages at startup and exec()s any line that
# starts with `import`, so our line always runs regardless of system files.
#
# Idempotent: re-running overwrites the two .pth files with the same content.
# Safe to run after every Aliyun `git pull` + deploy.
#
# Usage (on Aliyun):
#   cd /root/OmniGraph-Vault && bash scripts/apply_lightrag_atomic_write_patch.sh
#
# ingest cron uses venv-aim1; kb-api uses venv. Both get the .pth.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# .pth executable line: a *.pth line beginning with `import` is exec()'d by the
# site module at startup. MUST be a single physical line (no real newlines) —
# prepend the repo root to sys.path so `import lib...` resolves regardless of
# CWD, then apply the patch. Errors inside the imported module are swallowed by
# that module's own fail-soft try/except (lib.lightrag_atomic_write_patch.apply).
PTH_LINE='import os,sys; _r=os.environ.get("OMNIGRAPH_REPO_ROOT","'"${REPO_ROOT}"'"); (_r in sys.path) or sys.path.insert(0,_r); __import__("lib.lightrag_atomic_write_patch",fromlist=["apply"]).apply()'

applied=0
for venv in "$REPO_ROOT/venv-aim1" "$REPO_ROOT/venv"; do
  # Resolve the site-packages dir for whichever python layout exists.
  for sp in "$venv"/lib/python*/site-packages "$venv"/Lib/site-packages; do
    if [[ -d "$sp" ]]; then
      # zz_ prefix sorts the .pth last so any sys.path additions from other
      # .pth files (e.g. editable installs) are already in place.
      printf '%s\n' "$PTH_LINE" > "$sp/zz_omnigraph_atomic_write.pth"
      echo "  wrote $sp/zz_omnigraph_atomic_write.pth"
      # Best-effort cleanup of the superseded sitecustomize.py from the old
      # (pre-2026-06-11) approach, so we don't leave a dead file behind.
      rm -f "$sp/sitecustomize.py"
      applied=$((applied + 1))
      break
    fi
  done
done

if [[ "$applied" -eq 0 ]]; then
  echo "WARNING: no venv site-packages found under $REPO_ROOT (venv-aim1 / venv)" >&2
  exit 1
fi
echo "ISSUES #47 atomic-write .pth applied to $applied venv(s)."
