#!/usr/bin/env bash
# CONTRACT-01 + CONTRACT-02 grep hooks for lib/research/.
#
# CONTRACT-01: lib/research/ may import ONLY `from omnigraph_search.query import search`
#              from the KG side — no other omnigraph_search.* imports allowed.
# CONTRACT-02: ~/.hermes and omonigraph-vault paths may appear ONLY in
#              lib/research/config.py — zero hardcoded paths in any other file.
set -e

# CONTRACT-01: forbidden omnigraph_search imports outside .query
hits=$(grep -rE "from omnigraph_search" lib/research/ \
  --include='*.py' \
  | grep -vE "from omnigraph_search\.query " \
  | grep -vE "from omnigraph_search\.query$" \
  | grep -vE "import omnigraph_search\.query" \
  || true)
if [ -n "$hits" ]; then
  echo "CONTRACT-01 violation: forbidden omnigraph_search import in lib/research/"
  echo "$hits"
  exit 1
fi
echo "CONTRACT-01 ok"

# CONTRACT-02: no hardcoded ~/.hermes or omonigraph-vault paths outside config.py
hits2=$(grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
  | grep -vE "config\.py|README\.md|^Binary" \
  || true)
if [ -n "$hits2" ]; then
  echo "CONTRACT-02 violation: hardcoded ~/.hermes or omonigraph-vault path in lib/research/ outside config.py"
  echo "$hits2"
  exit 1
fi
echo "CONTRACT-02 ok"
