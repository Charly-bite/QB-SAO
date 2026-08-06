---
tags:
  - scripts
  - py
  - backfill
---
# 📊 scripts/backfill_auto_status.py

> **Historical status backfill** — retroactively assigns statuses from SAP data.

## Role
One-time or periodic script that reads historical SAP data (via hdbcli) and backfills order statuses that were missed during normal sync.

## Depends On
- `hdbcli` — Direct SAP HANA connection
- `dotenv` — Environment configuration

## Part Of
- [[Background_Jobs]], [[Scripts]]
