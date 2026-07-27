# Fix P2-01: Non-Blocking Write Queue with Timeout

## Priority: P2 (Medium Latency Risk)

### Problem Description
In `core/factura_metadata_manager.py` (line 76), `_enqueue_write()` used a blocking `Queue.put()` on a bounded queue (`maxsize=100`):

```python
self._write_queue.put((file_path, data))  # ← Default block=True indefinitely!
```

**Risk**: If the background worker thread (`_process_write_queue`) got stuck due to filesystem locks, high disk I/O, or a full storage volume, the web request thread calling `_save_fallback()` would **block indefinitely**, hanging user HTTP requests.

---

## Solution

Changed `.put()` to use `block=True, timeout=2` wrapped with a `queue.Full` exception handler:

```python
try:
    self._write_queue.put((file_path, data), block=True, timeout=2)
except queue.Full:
    logger.warning(
        f"JSON write queue full — dropping write for {file_path}. "
        "Data is already persisted to SQL."
    )
```

Because data is already safely stored in SQL Server, dropping a delayed JSON fallback write under severe disk degradation prevents web request thread freezes.

---

## Affected Files

- [core/factura_metadata_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/factura_metadata_manager.py#L75-L82)

---

## Verification

- Verified non-blocking queue behavior when queue capacity is saturated.
