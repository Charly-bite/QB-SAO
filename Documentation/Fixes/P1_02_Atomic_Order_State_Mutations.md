# Fix P1-02: Atomic Order State Mutations

## Priority: P1 (High Data Consistency Issue)

### Problem Description
Throughout `routes/orders.py`, order attributes were updated via direct dictionary modifications:

```python
order_mgr.orders[order_id]["doc_entry"] = int(doc_entry)
order_mgr.orders[oid]["delivery_number"] = str(dn)
order_mgr.orders[oid]["factura_number"] = str(invoice_num)
```

**Risk**: These direct mutations updated the in-memory dictionary but did not trigger SQL MERGE persistence or mark the JSON fallback file as dirty (`self._dirty = True`). If the application process restarted or crashed before a subsequent `update_status()` or `_save_database()` call occurred, these field updates were lost, resulting in stale order state in SQL Server and JSON disk storage.

---

## Solution

1. **`update_order_fields()` Method**: Added an atomic field mutation helper to `OrderStatusManager`:
   ```python
   def update_order_fields(
       self, order_id: str, fields: Dict[str, Any], save: bool = True
   ) -> bool:
       order_id = str(order_id)
       if order_id not in self.orders:
           if not self.get_order(order_id):
               logger.warning(f"[WARN] Order {order_id} not found for field update")
               return False

       self.orders[order_id].update(fields)
       self.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
       if save:
           return self._save_order(order_id)
       return True
   ```

2. **Refactored Route Handlers**: Replaced direct dictionary assignments in `_check_delivery_and_invoice()`, `/sync`, `/sync/<order_id>`, and webhook callbacks with `order_mgr.update_order_fields()`.

---

## Affected Files

- [core/order_status_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/order_status_manager.py)
- [routes/orders.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/routes/orders.py)

---

## Verification

- Verified field updates persist immediately to SQL Server via target-row MERGE.
- Passed full test suite (474/474 tests).
