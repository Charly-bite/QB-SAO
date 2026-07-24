# Fix P2-02: Active Orders Filtering Fix for Health Metrics

## Priority: P2 (Medium Metric Reporting Issue)

### Problem Description
In `core/order_status_manager.py` (line 574), `get_active_orders()` defined an empty list of inactive statuses:

```python
def get_active_orders(self) -> List[Dict[str, Any]]:
    inactive_statuses = []  # ← Bug: Always empty!
    active = [
        o for o in self.orders.values() if o.get("status") not in inactive_statuses
    ]
    return active
```

**Impact**: Because `inactive_statuses` was empty, `get_active_orders()` returned **all** orders in the system (including completed/shipped and cancelled orders).

The `/api/health/detailed` health endpoint reported `active_orders_loaded` as equal to total loaded orders (e.g. 4,399 instead of actual active non-shipped orders), rendering active order monitoring inaccurate.

---

## Solution

Populated `inactive_statuses` with terminal order states:

```python
def get_active_orders(self) -> List[Dict[str, Any]]:
    """Get orders that are not shipped or cancelled."""
    self.reload_if_needed()
    inactive_statuses = [OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value]
    active = [
        o for o in self.orders.values() if o.get("status") not in inactive_statuses
    ]
    active.sort(key=lambda x: x.get("order_date", ""), reverse=True)
    return active
```

---

## Affected Files

- [core/order_status_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/order_status_manager.py#L574)

---

## Verification

- Tested against health endpoint `/api/health/detailed`: `active_orders_loaded` now correctly returns 3,703 active orders (excluding shipped/cancelled orders).
