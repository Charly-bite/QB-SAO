---
tags:
  - scripts
  - py
  - daemon
---
# 🔁 scripts/sync_print_daemon.py

> **Print sync daemon wrapper** — loops `sync_print_jobs_job.py` on a schedule.

## Role
Daemon process that spawns the print sync job at regular intervals, managing subprocess lifecycle and logging.

## Related
- [[Node_scripts_sync_print_jobs_job_py]] — The actual sync job

## Part Of
- [[Background_Jobs]], [[Scripts]]
