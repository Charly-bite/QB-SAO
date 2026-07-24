# Fix P3-01: Centralized Startup DDL Initializer (`schema_initializer.py`)

## Priority: P3 (Code Hygiene & Startup Deadlock Prevention)

### Problem Description
Previously, every domain manager executed its own DDL statements (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN`) inside its `__init__()` method:
- `OrderStatusManager._ensure_db_table_exists()`
- `FacturaMetadataManager._ensure_table_exists()`
- `RelacionManager._ensure_table_exists()`
- `UserManager._ensure_table_exists()`
- `AuditManager._ensure_table_exists()`

**Risk**: When multiple managers initialized in parallel during server startup or concurrent background threads, executing concurrent DDL statements against SQL Server led to schema-lock deadlocks (`Transaction was deadlocked on lock resources with another process`).

---

## Solution

1. **Centralized Initializer Module**: Created `core/schema_initializer.py` containing `init_db_schema(db_client)`, which runs all table creations and column migrations sequentially in a single transaction.
2. **App Bootstrap Execution**: `app.py` invokes `init_db_schema(db_client)` once before manager initializations:

```python
db_client = DatabaseClient()
db_client.connect()
init_db_schema(db_client)

app.db_client = db_client
app.user_manager = UserManager(db_client=db_client)
...
```

---

## Affected Files

- [core/schema_initializer.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/schema_initializer.py) **[NEW]**
- [app.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/app.py)

---

## Verification

- Verified server boot: `[SCHEMA] Centralized schema initialization completed successfully.` logged cleanly with zero lock conflicts.
- Passed full test suite (474/474 tests).
