---
tags:
  - core
  - py
  - health
---
# 🩺 core/system_health.py

> System health check utilities.

## Role
Provides `check_sga_status()` function that tests network connectivity to the SGA (label printing system) via socket connection. Used in health endpoints and template context.

## Key Functions
- `check_sga_status()` — Returns `True` if SGA is reachable

## Depends On
- Standard library: `os`, `time`, `socket`

## Used By
- [[Node_app_py]] — Context processor (injects `sga_available` into all templates)
- Health check endpoints (`/health`, `/api/monitor/health`, `/api/health/detailed`)

## Part Of
- [[Core_Logic]]
