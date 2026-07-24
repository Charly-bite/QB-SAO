# Fix P1-01: Shared `DatabaseClient` Singleton (Connection Pool Consolidation)

## Priority: P1 (High Architectural Issue)

### Problem Description
Previously, each domain manager instantiated its own `DatabaseClient()` upon creation:
- `OrderStatusManager` → `DatabaseClient()`
- `FacturaMetadataManager` → `DatabaseClient()`
- `RelacionManager` → `DatabaseClient()`
- `UserManager` → `DatabaseClient()`
- `AuditManager` → `DatabaseClient()`

Each `DatabaseClient` creates a separate SQLAlchemy Engine with `pool_size=10` and `max_overflow=20`. This meant a single Flask application process could open up to **150 SQL Server connections** (5 × 30). Under peak user traffic, SQL Server hit maximum connection limits, causing random `pyodbc.OperationalError: [HY000] [Microsoft][ODBC Driver 17 for SQL Server] Connection limit exceeded` errors across random API routes.

---

## Solution

1. **Manager Constructor Update**: Updated the `__init__` methods of all 5 domain managers to accept an optional `db_client` argument:
   ```python
   def __init__(self, ..., db_client: Optional[Any] = None):
       if db_client is not None:
           self.db_client = db_client
           self.sql_engine = db_client.get_sql_engine()
       else:
           # Fallback for standalone scripts and isolated unit tests
           self.db_client = DatabaseClient()
           self.db_client.connect()
   ```

2. **Application Injection (`app.py`)**: `create_app()` creates a single `DatabaseClient` instance, connects it once, and injects it into all managers:
   ```python
   db_client = DatabaseClient()
   db_client.connect()

   app.db_client = db_client
   app.user_manager = UserManager(db_client=db_client)
   app.order_status_mgr = OrderStatusManager(db_client=db_client)
   app.factura_metadata_mgr = FacturaMetadataManager(db_client=db_client)
   app.relacion_mgr = RelacionManager(db_client=db_client)
   app.audit_mgr = AuditManager(db_client=db_client)
   ```

---

## Affected Files

- [app.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/app.py)
- [core/order_status_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/order_status_manager.py)
- [core/factura_metadata_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/factura_metadata_manager.py)
- [core/relacion_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/relacion_manager.py)
- [core/user_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/user_manager.py)
- [core/audit_manager.py](file:///mnt/c/Users/QB_DESARROLLO/SAO%20PROD/core/audit_manager.py)

---

## Verification

- Verified SQL connection count during server boot: reduced from 5 pools to 1 pool.
- Full test suite passed (474/474 tests).
