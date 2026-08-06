# Fix P0-03: Missing `import os` in SAP Sync Worker

## Priority: P0 (Critical Production Issue)

### Problem Description
In `core/sap_sync_worker.py` (line 41), the fallback connector initialization path attempted to read environment variables using `os.environ.get()`:

```python
if not sap:
    from core.sap_connector import SAPHanaConnector
    try:
        sap_user = os.environ.get("SAP_USER")  # ← NameError: name 'os' is not defined!
        sap_pass = os.environ.get("SAP_PASS")
        ...
```

**Impact**: If `app.sap_connector` failed to initialize at startup (e.g. SAP HANA was unreachable during app boot), every subsequent 60-second cycle of `SAPSyncWorker` failed immediately with `NameError: name 'os' is not defined`.

The worker was unable to reconnect automatically when SAP HANA became available again, resulting in an unrecoverable sync outage until the web server process was restarted.

---

## Solution

Added `import os` to the top of `core/sap_sync_worker.py`:

```python
import os
import threading
import time
import logging
```

---

## Affected Files

- [core/sap_sync_worker.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/sap_sync_worker.py#L1)

---

## Verification

- Verified imports and verified fallback reconnection logic in background worker tests.
