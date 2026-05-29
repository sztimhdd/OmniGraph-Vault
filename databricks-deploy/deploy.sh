#!/usr/bin/env bash
# databricks-deploy/deploy.sh — primary deploy entry point.
# Makefile `deploy:` target delegates to this script. Both Windows hosts
# (no GNU make) and Linux hosts (with make) execute the same code path.
#
# This file is the source of truth. Past failure mode (closed by promoting
# this file out of .scratch/): transient .scratch/deploy_inline_*.sh copies
# drifted from Makefile. The 2026-05-25 inline missed 3 critical --include
# flags (kg_synthesize.py / config.py / lib/**) and caused the arx-3
# singleton REGRESSION (graph reloaded per request, ~28s wall-time per
# synthesize call). Owning a single canonical script eliminates that drift.
#
# Usage:
#   bash databricks-deploy/deploy.sh
#   make -C databricks-deploy deploy
#   (run from any cwd — script cd's to repo root via $(dirname))

set -euo pipefail

WORKSPACE_ROOT=/Workspace/Users/hhu@edc.ca/omnigraph-kb
APP_NAME=omnigraph-kb
PROFILE=dev

cd "$(dirname "$0")/.."
echo ">>> CWD: $(pwd)"

echo ">>> Pass 0: refresh databricks-deploy/_ssg/ from kb/output/ (deploy-time SSG)"
rm -rf ./databricks-deploy/_ssg
cp -R ./kb/output ./databricks-deploy/_ssg
# Drop the inner .gitignore (`*` rule) that databricks sync would
# otherwise honor, excluding every file inside _ssg/ from upload.
rm -f ./databricks-deploy/_ssg/.gitignore

echo ">>> Pass 0b: flip KB_DEFAULT_LANG zh-CN -> en for Databricks audience"
find ./databricks-deploy/_ssg -name '*.html' -print0 | \
  xargs -0 sed -i 's|<html lang="zh-CN">|<html lang="en">|g; s|window\.KB_DEFAULT_LANG = "zh-CN"|window.KB_DEFAULT_LANG = "en"|g'

echo ">>> Pass 0c: stage project-root synthesize deps (kdb-3)"
rm -rf ./databricks-deploy/kg_synthesize.py ./databricks-deploy/config.py ./databricks-deploy/lib
cp ./kg_synthesize.py ./databricks-deploy/kg_synthesize.py
cp ./config.py ./databricks-deploy/config.py
cp -R ./lib ./databricks-deploy/lib

echo ">>> Pass 0d: rebrand _ssg for Databricks audience (Aliyun untouched)"
cp ./kb/kb-logo.png ./databricks-deploy/_ssg/static/VitaClaw-Logo-v0.png
find ./databricks-deploy/_ssg -name '*.html' -print0 | \
  xargs -0 sed -i \
    -e 's|VitaClaw-Logo-v0\.png|__KB_LOGO_FILE__|g' \
    -e 's|企小勤 / VitaClaw — AI Agent 技术圈双语知识库|EDC Agentic AI Knowledge Base|g' \
    -e 's|企小勤知识库 — AI Agent 技术内容站|EDC Agentic AI Knowledge Base|g' \
    -e 's|企小勤 / VitaClaw|EDC Agentic AI Knowledge Base|g' \
    -e 's|企小勤 VitaClaw|EDC Agentic AI Knowledge Base|g' \
    -e 's|VitaClaw 企小勤|EDC Agentic AI Knowledge Base|g' \
    -e 's|VitaClaw|EDC Agentic AI Knowledge Base|g' \
    -e 's|企小勤|EDC Agentic AI Knowledge Base|g' \
    -e 's|__KB_LOGO_FILE__|VitaClaw-Logo-v0.png|g'
sed -i \
  -e "s|if (l.indexOf('zh') === 0) return 'zh-CN';|if (l.indexOf('zh') === 0) return DEFAULT_LANG;|" \
  -e "s|if (l.indexOf('en') === 0) return 'en';|if (l.indexOf('en') === 0) return DEFAULT_LANG;|" \
  ./databricks-deploy/_ssg/static/lang.js

echo ">>> Pass 1: sync databricks-deploy/* -> workspace/databricks-deploy/"
# CRITICAL --include set (verified against Makefile @ commit 7eeab18 line 116-121):
#   1. _ssg/**          — pre-rendered SSG output (.gitignore L91)
#   2. kg_synthesize.py — Pass-0c project-root LightRAG entry (L94)
#   3. config.py        — Pass-0c project-root config (L93)
#   4. lib/**           — Pass-0c project-root LLM/embed providers (L92)
# Without all 4, sync silently skips and you get arx-3 singleton REGRESSION.
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" sync --full \
  --include "_ssg/**" \
  --include "kg_synthesize.py" \
  --include "config.py" \
  --include "lib/**" \
  ./databricks-deploy "$WORKSPACE_ROOT/databricks-deploy"

echo ">>> Pass 2: sync kb/* -> workspace/databricks-deploy/kb/"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" sync --full \
  ./kb "$WORKSPACE_ROOT/databricks-deploy/kb"

echo ">>> Deploy app from $WORKSPACE_ROOT/databricks-deploy"
MSYS_NO_PATHCONV=1 databricks --profile "$PROFILE" apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_ROOT/databricks-deploy"

databricks --profile "$PROFILE" apps get "$APP_NAME" -o json

echo ""
echo ">>> Deploy complete. Verify deployment_id + status above."
