# 🛠️ Scripts & Tooling

> `scripts/` — Standalone utilities for deployment, auditing, syncing, and administration.

## Script Categories

### 🔄 Sync Scripts
| Script | File | Purpose |
|--------|------|---------|
| **Sync Orders** | [[Node_scripts_sync_orders_job_py]] | SAP HANA → local SQL order sync |
| **Sync Print Jobs** | [[Node_scripts_sync_print_jobs_job_py]] | SGA print events → order status |
| **Print Daemon** | [[Node_scripts_sync_print_daemon_py]] | Daemon wrapper for print sync |
| **OpenOMS Sync Service** | [[Node_scripts_openoms_sync_service_py]] | Windows service wrapper |

### 🔍 Audit Scripts
| Script | File | Purpose |
|--------|------|---------|
| **Audit SQL** | [[Node_scripts_audit_sql_py]] | Audit SQL Server data integrity |
| **Audit JSON** | [[Node_scripts_audit_json_py]] | Audit JSON data files |
| **Audit SGA↔SAO** | [[Node_scripts_audit_sga_sao_py]] | Compare SGA and SAO states |

### 🔧 Repair & Admin
| Script | File | Purpose |
|--------|------|---------|
| **Repair Sync** | [[Node_scripts_repair_sync_py]] | Fix sync discrepancies |
| **Reset Admin** | [[Node_scripts_reset_admin_py]] | Reset admin password |
| **Backfill Status** | [[Node_scripts_backfill_auto_status_py]] | Backfill historical statuses from SAP |

### 🚀 Deployment
| Script | Purpose |
|--------|---------|
| `deploy_dev.bat` | Deploy to development |
| `deploy_prod.bat` | Deploy to production |
| `install_sync_service.bat` | Install sync Windows service |
| `uninstall_sync_service.bat` | Remove sync service |
| `run_tests.bat` | Run test suite |
| `pre_commit_check.bat` | Pre-commit validation |

See also: [[README_SYNC]] for sync service documentation.

---
*Part of [[Home]] architecture*
