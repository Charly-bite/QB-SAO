# Fix P1-03: JSON Save Deepcopy Concurrency Guard

## Priority: P1 (High Concurrency Crash Risk)

### Problem Description
In `core/order_status_manager.py` (line 288), `_save_database()` constructed the JSON payload directly from the active `self.orders` dictionary:

```python
with self._json_write_lock:
    data = {"orders": self.orders, "last_updated": last_updated}  # ← No deepcopy!
    json.dump(data, f, indent=2, ensure_ascii=False)
```

**Risk**: While `json.dump()` iterated over `self.orders`, concurrent worker threads (such as `SAPSyncWorker` or background webhook retries) could mutate `self.orders` simultaneously (adding new orders or modifying `status_history`). This triggered `RuntimeError: dictionary changed size during iteration` or generated corrupted/truncated JSON files on disk.

---

## Solution

Applied `copy.deepcopy()` before passing the dictionary to `json.dump()`:

```python
with self._json_write_lock:
    data = {"orders": copy.deepcopy(self.orders), "last_updated": last_updated}
    dir_name = os.path.dirname(self.db_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    ...
```

---

## Affected Files

- [core/order_status_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/order_status_manager.py#L286-L290)

---

## Verification

- Verified concurrent writes under multi-threaded load tests (`tests/test_order_routes_full.py`).
