# Phase 1: Discussion Log

**Date:** 2026-04-21
**Areas discussed:** Entity buffer path, Fix scope, skill_runner test design

---

## Q1: Where should ENTITY_BUFFER_DIR live?

Options presented:
- Runtime data dir (~/.hermes/omonigraph-vault/entity_buffer/) — consistent with BASE_DIR
- Project root (OmniGraph-Vault/entity_buffer/) — current implied behavior
- You decide

**User selected:** Runtime data dir (~/.hermes/omonigraph-vault/entity_buffer/)

---

## Q2: How strict should the Phase 1 fix scope be?

Options presented:
- Strictly INFRA-01..04 only
- INFRA-01..04 + bare except clauses
- INFRA-01..04 + all adjacent bugs

**User selected:** INFRA-01..04 + all adjacent bugs (all 7 items from CONCERNS.md)

---

## Q3: What should the skill_runner test for GATE6-05 cover?

Options presented:
- Trigger phrases only (minimal)
- Trigger phrases + key guard clauses
- Full test suite (triggers + guards + wrong-skill)

**User selected:** Full test suite — existing test file has 8 cases; add non-WeChat URL guard case
