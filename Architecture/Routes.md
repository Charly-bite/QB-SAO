# 🌐 Routes & API Endpoints

> `routes/` — Flask blueprints that define all HTTP endpoints. Registered in [[App_Factory]].

## Blueprint Overview

| Blueprint | Prefix | File | Purpose |
|-----------|--------|------|---------|
| **auth_bp** | `/` | [[Node_routes_auth_py]] | Login, logout, password change |
| **orders_bp** | `/orders` | [[Node_routes_orders_py]] | Main order UI + all API endpoints |
| **users_bp** | `/users` | [[Node_routes_users_py]] | User management CRUD |

## Auth Blueprint — [[Node_routes_auth_py]]

| Route | Method | Description | Template |
|-------|--------|-------------|----------|
| `/login` | GET/POST | Login page & authentication | [[Node_templates_auth_login_html]] |
| `/logout` | GET | Session destroy + redirect | — |
| `/change-password` | GET/POST | Force password change | [[Node_templates_auth_change_password_html]] |

**Dependencies**: [[Node_extensions_py]] (limiter, current_app), [[Node_models_py]] (User class)

## Orders Blueprint — [[Node_routes_orders_py]]

The **largest file** in the project (3700+ lines). Handles:

### UI Pages
| Route | Template | Description |
|-------|----------|-------------|
| `/orders/` | [[Node_templates_orders_index_html]] | Orders list with filters |
| `/orders/monitor` | [[Node_templates_orders_monitor_html]] | Real-time TV monitor |
| `/orders/facturas` | [[Node_templates_orders_facturas_html]] | Invoice management |
| `/orders/<id>` | [[Node_templates_orders_detail_html]] | Single order detail |
| `/orders/dashboard` | [[Node_templates_orders_dashboard_html]] | Analytics dashboard |
| `/orders/visor` | [[Node_templates_orders_visor_html]] | Seller order visor |
| `/orders/auditoria` | [[Node_templates_orders_auditoria_html]] | Audit log viewer |
| `/orders/tiempos-tv` | [[Node_templates_orders_tiempos_tv_html]] | TV time display |

### JSON API Endpoints
| Route | Method | Purpose |
|-------|--------|---------|
| `/orders/api/orders` | GET | Fetch orders list (JSON) |
| `/orders/api/update-status` | POST | Update order status |
| `/orders/api/sga-label-printed` | POST | SGA webhook (CSRF-exempt) |
| `/orders/api/relaciones/*` | GET/POST | Relación de envíos API |
| `/orders/api/facturas/*` | GET/POST | Factura metadata API |
| `/orders/stream` | GET | SSE real-time event stream |
| `/api/monitor/health` | GET | Health check (JSON) |

**Dependencies**: [[Node_core_order_status_manager_py]], [[Node_core_sap_connector_py]], [[Node_core_user_manager_py]]

## Users Blueprint — [[Node_routes_users_py]]

| Route | Method | Template | Description |
|-------|--------|----------|-------------|
| `/users/` | GET | [[Node_templates_users_list_html]] | User list |
| `/users/create` | GET/POST | [[Node_templates_users_form_html]] | Create user |
| `/users/<id>/edit` | GET/POST | [[Node_templates_users_form_html]] | Edit user |

**Dependencies**: [[Node_extensions_py]] (current_app), [[Node_core_user_manager_py]] (UserRole)

---
*Part of [[Home]] architecture*
