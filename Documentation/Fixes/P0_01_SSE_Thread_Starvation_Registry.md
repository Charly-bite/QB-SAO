# Fix P0-01: SSE Thread Starvation & Connection Registry

## Priority: P0 (Critical Production Issue)

### Problem Description
On July 23, 2026, Credit department users approved invoices, but Billing users were locked out from submitting shipping relations until the Credit user logged out.

**Root Cause**: Waitress runs with a fixed pool of 200 worker threads. Server-Sent Events (SSE) endpoints `/orders/stream` and `/orders/stream_web` used an unmanaged `_SUBSCRIBERS` list. Each open tab held an HTTP connection open indefinitely, taking up a Waitress thread. When multiple users kept multiple tabs open (and monitor pages opened redundant connections), all 200 threads were exhausted by idle SSE loops, starving normal REST API requests (like invoice selection and saving).

---

## Solution & Architecture

### 1. `_SSERegistry` Class (`routes/orders.py`)
Replaced the `_SUBSCRIBERS = []` list with a thread-safe registry class enforcing two hard limits:
- **Per-User Limit**: Maximum 3 active SSE connections per user account (covers 2–3 browser tabs).
- **Global Subscriber Limit**: Hard cap of 100 total SSE connections system-wide (reserving 100 of 200 Waitress threads exclusively for API requests).

### 2. Poison-Pill Eviction Pattern
When a user exceeds 3 connections, or the global cap is reached, `_SSERegistry` injects a `None` poison-pill into the queue of the oldest connection. The SSE generator checks for `data is None`, immediately breaks out of its streaming loop, and finishes the response—freeing the Waitress worker thread.

### 3. Frontend Deduplication (`base.html`, `monitor.html`, `monitor_mostrador.html`)
- `base.html` introduced `window._globalES` and `window._globalSSETimer` to prevent redundant connections from `base.html` initialization.
- Added `window.__skipGlobalSSE = true` in `monitor.html` and `monitor_mostrador.html` so specialized monitor pages skip the global SSE stream and only maintain their own dedicated SSE connection (reducing connections per monitor tab from 2 to 1).

### 4. Health Endpoint Observability (`app.py`)
Exposed SSE metrics in `GET /api/health/detailed`:
- `sse_connections`: Current count of active subscribers.
- `sse_connections_by_user`: Dictionary mapping username to active connection count.

---

## Affected Files

- [routes/orders.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/routes/orders.py)
- [templates/base.html](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/templates/base.html)
- [templates/orders/monitor.html](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/templates/orders/monitor.html)
- [templates/orders/monitor_mostrador.html](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/templates/orders/monitor_mostrador.html)
- [app.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/app.py)
- [tests/test_sse_registry.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/tests/test_sse_registry.py)

---

## Verification

- Tested via `tests/test_sse_registry.py`: 11 concurrency, eviction, and isolation tests passed.
- Verified `/api/health/detailed` accurately reports active SSE metrics.
