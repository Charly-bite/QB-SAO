# Fix P0-02: `traceback.logger.warning_exc()` AttributeError Crash

## Priority: P0 (Critical Production Issue)

### Problem Description
In `core/order_status_manager.py` (line 283), the exception handler inside `_save_database()` contained:

```python
except Exception as e:
    import traceback
    logger.warning(f"[WARN] Error saving to SQL: {e}")
    traceback.logger.warning_exc()  # ← BUG: AttributeError!
```

**Impact**: When `_save_database()` encountered a transient SQL error (e.g. database connection timeout, temporary network hiccup, or SQL Server reboot), Python raised `AttributeError: module 'traceback' has no attribute 'logger'`.

This error propagated up through the exception handler, **hiding the original SQL error**, breaking caller loops, and causing background daemon threads like `SAPSyncWorker` to crash silently. Once the worker thread crashed, **all SAP synchronization stopped permanently** until a manual server restart.

---

## Solution

Replaced the invalid `traceback.logger.warning_exc()` call with standard Python `logger.warning(..., exc_info=True)` logging:

```python
except Exception as e:  # pragma: no cover
    logger.warning(f"[WARN] Error saving to SQL: {e}", exc_info=True)
```

---

## Affected Files

- [core/order_status_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/order_status_manager.py#L280-L285)

---

## Verification

- Verified syntax and verified exception handling in unit tests.
- Re-tested `_save_database()` SQL fallback handling.
