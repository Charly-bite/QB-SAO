# Open-OMS — Project Context & Structure Reference

> **Purpose of this file:** A living reference document describing the architecture, modules, conventions, and data flows of this project for future developers (and AI assistants).

---

## 1. What Is This App?

**Open-OMS** is a Flask-based internal order-tracking web application for a company using SAP Business One. It allows warehouse operators, sellers, and managers to monitor the lifecycle of sales orders — from the moment they are created in SAP through to final delivery.

The app is completely **independent from the SAP system**: it maintains its own local tracking database and only reads from SAP (never writes back).

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | Flask 3.x (Python) |
| Auth | Flask-Login + Flask-WTF (CSRF) |
| Rate Limiting | Flask-Limiter |
| Templates | Jinja2 + Tailwind CSS + Alpine.js |
| Local DB | SQL Server (via PyODBC + SQLAlchemy) |
| SAP Source | SAP Business One / HANA (via `hdbcli`) |
| Background Job | `sync_orders_job.py` (Windows Task Scheduler) |
| Tests | Pytest + pytest-cov + pytest-flask |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) |

---

## 3. Directory Structure

```
Open-OMS/
│
├── app.py                    # Application factory (create_app), entry point
├── config.py                 # Multi-environment configuration classes
├── extensions.py             # Shared Flask extensions (Flask-Limiter)
├── models.py                 # Flask-Login User model (wraps UserManager data)
├── sync_orders_job.py        # Standalone background sync job (SAP → local DB)
├── reset_admin.py            # One-off script to reset admin credentials
├── run.bat                   # Windows batch launcher for the dev server
│
├── core/                     # Business logic (no Flask dependency)
│   ├── __init__.py
│   ├── database_client.py    # SQL Server connectivity (PyODBC + SQLAlchemy)
│   ├── order_status_manager.py  # Order CRUD, status lifecycle, DB persistence
│   ├── order_status_db.json  # JSON fallback when SQL is unavailable
│   ├── sap_connector.py      # SAP HANA connector (hdbcli); optional dependency
│   └── user_manager.py       # User CRUD, auth, role management → SQL persistence
│
├── routes/                   # Flask blueprints (thin controllers)
│   ├── __init__.py
│   ├── auth.py               # Blueprint: auth — /login, /logout, /change-password
│   └── orders.py             # Blueprint: orders — all order & API routes
│
├── middleware/
│   └── request_logger.py     # before/after_request hooks for HTTP access logging
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Master layout (Tailwind, Alpine, nav, flash messages)
│   ├── auth/
│   │   ├── login.html
│   │   └── change_password.html
│   ├── orders/
│   │   ├── index.html        # Main order dashboard (table, filters, status controls)
│   │   ├── detail.html       # Single order detail page
│   │   ├── monitor.html      # Public TV/monitor display (auto-refresh)
│   │   └── visor.html        # Seller self-service visor (read-only)
│   └── errors/
│       ├── 404.html
│       └── 500.html
│
├── static/
│   ├── css/
│   │   ├── tailwind.css      # Compiled Tailwind base
│   │   └── monitor.css       # Custom styles for the monitor/TV view
│   ├── js/
│   │   ├── tailwind.js       # Tailwind CDN/config
│   │   └── alpine.min.js     # Alpine.js for reactive UI
│   └── images/
│       ├── logo_vertical.2.png
│       └── sap-business-one-logo.png
│
├── tests/                    # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py           # Fixtures: mock DB, test app, role-based clients
│   ├── test_auth.py          # Login, logout, password-change tests
│   ├── test_health.py        # /health endpoint smoke test
│   ├── test_order_status_manager.py  # OrderStatusManager unit tests
│   ├── test_orders.py        # Order route integration tests
│   └── test_user_manager.py  # UserManager unit tests
│
├── scripts/
│   ├── deploy_dev.bat        # Dev deployment helper
│   ├── pre_commit_check.bat  # Pre-commit syntax/lint check
│   └── run_tests.bat         # Test runner shortcut
│
├── logs/                     # Runtime log files (gitignored)
│   └── seguimiento.log       # Combined app log (also stdout)
│
├── .github/workflows/
│   └── ci.yml                # GitHub Actions: test matrix (Py 3.12 & 3.13) + lint
│
├── requirements.txt          # Production dependencies
├── requirements-dev.txt      # Dev/test extras (pytest, coverage)
├── .coveragerc               # Coverage configuration
└── .gitignore
```

---

## 4. Application Factory (`app.py`)

The app uses the **factory pattern** via `create_app(config_name=None)`.

**Initialization order inside `create_app`:**
1. Load config class from `config.py` (keyed by `FLASK_ENV` env var or explicit arg).
2. Init CSRF protection (`Flask-WTF`) with a graceful expired-session redirect.
3. Init rate limiter (`Flask-Limiter`) from `extensions.py`.
4. Init `Flask-Login` with `login_view = 'auth.login'`.
5. Instantiate `UserManager` and `OrderStatusManager` (stored on `app`).
6. Optionally instantiate `SAPHanaConnector` if `hdbcli` is installed and env credentials are present.
7. Register blueprints: `auth_bp` (no prefix) and `orders_bp` (prefix `/orders`).
8. Hook request logger middleware.
9. Register error handlers (404, 500) — JSON for API paths, HTML otherwise.
10. Register utility context processors (exposes `UserRole`, `OrderStatus`, `sap_available` to all templates).

**App-level attributes set at startup:**

| `app.*` | Type | Description |
|---|---|---|
| `app.user_manager` | `UserManager` | Singleton user store |
| `app.order_status_mgr` | `OrderStatusManager` | Singleton order store |
| `app.sap_connector` | `SAPHanaConnector \| None` | SAP connection (lazy) |
| `app.sap_available` | `bool` | Whether `hdbcli` could be imported |
| `app.limiter` | `Limiter` | Rate limiter instance |
| `app.csrf` | `CSRFProtect` | CSRF instance |

---

## 5. Configuration (`config.py`)

Four environment classes, selected via `FLASK_ENV`:

| Class | `FLASK_ENV` value | Key differences |
|---|---|---|
| `DevelopmentConfig` | `development` (default) | `DEBUG=True`, no HTTPS required |
| `StagingConfig` | `staging` | `DEBUG=False`, cookie security off |
| `ProductionConfig` | `production` | `DEBUG=False`, `SESSION_COOKIE_SECURE=True`, rotating file log |
| `TestingConfig` | `testing` | `TESTING=True`, CSRF disabled, rate limiter disabled |

**Secret key** is auto-generated and persisted in `.flask_secret_key` (or read from `SECRET_KEY` env var).

**Session lifetime:** 8 hours (`PERMANENT_SESSION_LIFETIME`).

---

## 6. Core Layer (`core/`)

### 6.1 `DatabaseClient` (`database_client.py`)

Wraps SQL Server connectivity via **PyODBC + SQLAlchemy**.

- Builds a connection string from env vars: `SQL_SERVER`, `SQL_DATABASE`, `SQL_USER`, `SQL_PASSWORD`, `SQL_DRIVER`, `SQL_TRUST_CERTIFICATE`.
- Default target: `192.168.2.237` → `SGA_Database`.
- Auto-detects the best available ODBC driver if `SQL_DRIVER` is not set.
- Exposes `connect() → bool`, `get_sql_engine()`, and `execute_query(sql, params)`.
- Both `UserManager` and `OrderStatusManager` instantiate their own `DatabaseClient`.

### 6.2 `OrderStatusManager` (`order_status_manager.py`)

The heart of the tracking system.

**Dual-table database strategy:**
- **Reads from** `order_status` table (written by the separate SGA_dev app).
- **Writes to** `seguimiento_order_status` table (this app's own tracking layer).
- Falls back to `core/order_status_db.json` when SQL Server is unreachable.

**`OrderStatus` enum values (workflow pipeline):**

```
Pendiente → En Proceso → Terminado → Facturacion →
Relacion de envio → Enviado al cliente
                                          ↘ Cancelado / En Espera
```

**Key methods:**

| Method | Purpose |
|---|---|
| `import_from_sap(sap_order)` | Upsert a single SAP order; preserves existing local status |
| `bulk_import_from_sap(orders)` | Batch upsert from SAP list |
| `update_status(order_id, new_status, user, notes)` | Transition status + append to history |
| `get_all_orders()` | All orders, sorted by `last_updated` desc |
| `get_active_orders()` | Orders excluding Shipped/Cancelled |
| `get_order_count_by_status()` | Dict of `{status: count}` |
| `reconcile_statuses()` | Fix mismatches between `sap_status` and local `status` |
| `export_for_web()` | Serializable list for JSON API responses |

**Order record schema:**
```
{
  order_id, customer_code, customer_name,
  order_date, delivery_date, total, currency, comments,
  items: [{ItemCode, Dscription, Quantity, ...}],
  sap_status,        # "Abierto" | "Cerrado" | "Cancelado"
  status,            # One of OrderStatus enum values
  status_history: [{status, previous_status, timestamp, user, notes}],
  imported_at, last_updated, updated_by, created_by,
  factura_number     # SAP invoice number (optional)
}
```

**Label migration map** (`STATUS_LABEL_MIGRATIONS`): Automatically normalizes legacy status strings on load.

### 6.3 `UserManager` (`user_manager.py`)

Manages users in the `seguimiento_users` SQL Server table.

- Password hashing: SHA-256 with per-user random salt (`secrets.token_hex(16)`).
- If the `seguimiento_users` table is empty, a default `admin / admin123` account is created.
- Upsert uses a raw `IF EXISTS … UPDATE … ELSE INSERT` pattern (no ORM).

**`UserRole` enum:**

| Role | Level | Permissions |
|---|---|---|
| `viewer` | 0 | Read-only access to orders |
| `seller` | 0 | Read-only; sees only own orders in monitor |
| `sell_manager` | 1 | Read-only; can see all seller orders with filter |
| `operator` | 1 | Can update order status and print labels |
| `admin` | 2 | Full access: manage users, all order operations |

**Key methods:** `authenticate`, `get_user`, `get_all_users`, `create_user`, `update_user`, `delete_user`.

### 6.4 `SAPHanaConnector` (`sap_connector.py`)

Optional dependency — only loaded if `hdbcli` is installed.

- Connects to SAP HANA at `SAP_HOST:SAP_PORT` (default `20.0.1.9:30015`) with schema `SBO_QUIMICABOSS`.
- Uses **thread-local connections** (`threading.local()`) for safety.
- Lazy connection: `_ensure_connected()` is called before each query.
- Credentials from env: `SAP_USER`, `SAP_PASS`, `SAP_HOST`, `SAP_PORT`, `SAP_SCHEMA`.

**SAP tables used:**

| Alias | SAP Table | Purpose |
|---|---|---|
| `sales_orders` | `ORDR` | Order headers |
| `sales_order_lines` | `RDR1` | Order line items |
| `customers` | `OCRD` | Customer master |
| `invoices` | `OINV` | Invoice headers |
| `invoice_lines` | `INV1` | Invoice lines |
| `delivery_notes` | `ODLN` | Delivery headers |
| `delivery_lines` | `DLN1` | Delivery lines |

**Key query methods:**
- `get_sales_orders(days_back, limit)` — pandas DataFrame of recent orders.
- `get_order_details(order_number)` — Full header + line items dict.
- `get_recent_orders(limit, only_open)` — Detailed list.
- `get_orders_status_batch(order_numbers)` — Efficient batch SAP-status lookup.

---

## 7. Routes (`routes/`)

### 7.1 Auth Blueprint (`auth.py`) — no prefix

| Method | URL | Description |
|---|---|---|
| GET/POST | `/login` | Login page; rate-limited to 5 POST/min per IP |
| GET | `/logout` | Logout (login required) |
| GET/POST | `/change-password` | Password change (login required) |

### 7.2 Orders Blueprint (`orders.py`) — prefix `/orders`

**Protected (login required):**

| Method | URL | Description |
|---|---|---|
| GET | `/orders/` | Main dashboard: order list with status/search filters |
| GET | `/orders/<id>` | Order detail page |
| POST | `/orders/<id>/update-status` | Update local order status (operator+) |
| POST | `/orders/import-sap` | Import a single order from SAP by order number |
| POST | `/orders/load-recent-sap` | Pull and import recent/open orders from SAP |
| POST | `/orders/sync-sap-status` | Reconcile SAP statuses for all tracked orders |
| POST | `/orders/add-manual` | Add a manual order record |
| POST | `/orders/<id>/delete` | Delete an order from tracking |

**Seller-specific:**

| Method | URL | Description |
|---|---|---|
| GET | `/orders/visor` | Seller self-service view (read-only, filtered to own orders) |
| GET | `/orders/api/visor-sync` | JSON API for visor auto-refresh |

**Monitor (public TV display):**

| Method | URL | Description |
|---|---|---|
| GET | `/orders/monitor` | Public monitor/TV display |
| GET | `/orders/api/active-orders` | JSON: active orders (login required) |
| GET | `/orders/api/seller-orders` | JSON: orders for a specific seller |

**Public API (token-protected via `X-Monitor-Token` header or `?token=` query param):**

| Method | URL | Description |
|---|---|---|
| GET | `/orders/public/active` | JSON: active orders |
| POST | `/orders/public/sync` | Full sync from SAP + reconcile |
| GET | `/orders/api/refresh` | Full refresh with SAP status update (JSON) |
| GET | `/orders/api/list` | Paginated order list (JSON) |
| GET | `/orders/public/weather` | Cached weather data (OpenWeatherMap) |

**Token protection:** If `MONITOR_TOKEN` env var is set, all `public/*` endpoints require `X-Monitor-Token` header or `?token=` param. If not set, endpoints are open (backward compatible).

---

## 8. Models (`models.py`)

`User` extends `flask_login.UserMixin`. Wraps a `UserManager` user dict.

**Properties / methods relevant to authorization:**

| Method | Description |
|---|---|
| `is_admin()` | `role == ADMIN` |
| `is_operator()` | `role in [ADMIN, OPERATOR]` |
| `is_seller()` | `role == SELLER` |
| `is_sell_manager()` | `role == SELL_MANAGER` |
| `can_see_all_orders()` | `role in [ADMIN, OPERATOR, SELL_MANAGER]` |
| `can_print_labels()` | `role in [ADMIN, OPERATOR]` |
| `can_manage_users()` | `role == ADMIN` |
| `has_role(role)` | Hierarchical role check |

---

## 9. Middleware (`middleware/`)

### `request_logger.py`

Hooks `before_request` / `after_request` to log every non-static HTTP request:

```
METHOD /path → STATUS (Xms) [user=username, ip=1.2.3.4]
```

- Uses `logger.error` for 5xx, `logger.warning` for 4xx, `logger.info` for 2xx/3xx.
- Static files and `/favicon.ico` are skipped.
- Logger name: `seguimiento.requests`.

---

## 10. Background Job (`sync_orders_job.py`)

A standalone script that syncs SAP orders into the local DB.

**Run manually:** `python sync_orders_job.py`
**Schedule:** Windows Task Scheduler (recommended: every 5–15 minutes).

**Logic:**
1. Creates a full Flask app context.
2. Connects to SAP via `SAPHanaConnector`.
3. Fetches up to 100 recent orders from SAP.
4. For each order:
   - If already tracked: update `sap_status` and `factura_number` if changed. Auto-transition local status to `Facturacion` if SAP status becomes `Cerrado`.
   - If new: `import_from_sap()` with status `Pendiente`.
5. Calls `_save_database()` only if there were changes.

---

## 11. Testing (`tests/`)

All external dependencies are mocked — no SQL Server or SAP HANA required.

### Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---|---|---|
| `_mock_database_client` | session | Patches `pyodbc` and `create_engine` to prevent real DB connections |
| `app` | function | Full Flask test app with temp JSON order DB seeded with 2 orders |
| `client` | function | Unauthenticated Flask test client |
| `auth_client` | function | Logged-in admin test client |
| `operator_client` | function | Logged-in operator test client |
| `viewer_client` | function | Logged-in viewer test client |
| `seller_client` | function | Logged-in seller (sap_seller_name=`system`) |
| `sell_manager_client` | function | Logged-in sell_manager test client |

### Test files

| File | Covers |
|---|---|
| `test_auth.py` | Login flow, invalid creds, logout, password change |
| `test_health.py` | `/health` endpoint response |
| `test_order_status_manager.py` | OrderStatusManager unit: CRUD, status transitions, reconcile |
| `test_orders.py` | Order route integration: index, detail, status update, role gating |
| `test_user_manager.py` | UserManager unit: create, auth, update, delete |

### Running tests

```
pytest tests/ -v --cov=. --cov-report=term-missing
```

Or use the batch shortcut: `scripts/run_tests.bat`

---

## 12. CI/CD (`.github/workflows/ci.yml`)

Triggered on push/PR to `main` or `develop`.

**Jobs:**
1. **`test`** — Matrix: Python 3.12 and 3.13 on `windows-latest`. Runs full pytest suite with coverage. Uploads `coverage.xml` as artifact.
2. **`lint`** — Python 3.12 on `windows-latest`. Runs `python -m py_compile` on all key source files.

---

## 13. Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | No | Auto-generated | Flask secret key |
| `FLASK_ENV` | No | `development` | Config class selector |
| `SQL_SERVER` | Yes (prod) | `192.168.2.237` | SQL Server host |
| `SQL_DATABASE` | No | `SGA_Database` | Database name |
| `SQL_USER` | No | `sga_app_user` | SQL login |
| `SQL_PASSWORD` | **Yes** | — | SQL password |
| `SQL_DRIVER` | No | Auto-detected | ODBC driver string |
| `SQL_TRUST_CERTIFICATE` | No | `yes` | Trust server cert |
| `SAP_HOST` | No | `20.0.1.9` | SAP HANA host |
| `SAP_PORT` | No | `30015` | SAP HANA port |
| `SAP_USER` | No | — | SAP login |
| `SAP_PASS` | No | — | SAP password |
| `SAP_SCHEMA` | No | `SBO_QUIMICABOSS` | SAP schema |
| `MONITOR_TOKEN` | No | — | Token for public API endpoints |

All variables are loaded from a `.env` file at startup via `python-dotenv`.

---

## 14. Key Design Decisions

1. **No ORM for users/orders** — Raw SQL via `exec_driver_sql` and PyODBC cursors to avoid schema migration complexity.
2. **JSON fallback** — `order_status_db.json` ensures the app keeps running even if SQL Server is unreachable.
3. **SAP is read-only** — The app never writes back to SAP. Status management is fully local.
4. **Thread-local SAP connections** — `SAPHanaConnector` uses `threading.local()` to allow safe concurrent use in Flask's threaded server.
5. **Factory pattern** — `create_app()` enables clean test isolation via `TestingConfig` and fixture-level overrides.
6. **Role hierarchy** — `has_role()` uses a numeric hierarchy dict so permissions compose cleanly.
7. **Status label migration** — `STATUS_LABEL_MIGRATIONS` dict allows renaming statuses in the enum without breaking historical data.



---
*Graph Context: Return to [[Home]] (Architecture)*
