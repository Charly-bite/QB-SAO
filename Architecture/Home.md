# 🏠 Open-OMS — Architecture Map

Welcome to the **Open-OMS** architecture vault. This knowledge graph maps how every file and component connects in the SAO order-tracking system.

---

## 🧱 System Layers

| Layer | Description | Entry Point |
|-------|-------------|-------------|
| 🏭 **Application Factory** | Flask app bootstrap, extension init, blueprint registration | [[App_Factory]] |
| 🧠 **Core Logic** | Business managers: orders, users, facturas, relaciones, auditing | [[Core_Logic]] |
| 🗄️ **Database** | SQL Server (local) + SAP HANA (ERP read-only) | [[Database]] |
| 🌐 **Routes & API** | Flask blueprints: auth, orders, users | [[Routes]] |
| 🎨 **Frontend** | Jinja2 templates, CSS, JS, Alpine.js reactivity | [[Frontend]] |
| ⚙️ **Background Jobs** | Sync daemons, print jobs, order backfill | [[Background_Jobs]] |
| 🔒 **Security** | CSRF, rate limiting, session management, role-based access | [[Security]] |
| 🧪 **Testing** | Unit tests for monitor and shipping | [[Testing]] |
| 🛠️ **Scripts & Tooling** | Audit, repair, deploy, admin reset utilities | [[Scripts]] |
| 📡 **Middleware** | Request logging, performance tracking | [[Middleware]] |

---

## 🔀 Data Flow Overview

```
SAP HANA (ERP) ──read──▶ SAPHanaConnector ──▶ OrderStatusManager ──▶ SQL Server (local)
                                                      │
                                                      ▼
                                              routes/orders.py
                                                      │
                                              ┌───────┴────────┐
                                              ▼                ▼
                                        HTML Templates    JSON API
                                        (monitor, index)  (/api/*)
```

---

## 📦 Component File Nodes

### Application Core
- [[Node_app_py]] — Main application factory + entry point
- [[Node_config_py]] — Multi-environment configuration
- [[Node_extensions_py]] — Shared Flask extensions (limiter, typed current_app)
- [[Node_models_py]] — User model for Flask-Login

### Core Business Logic (`core/`)
- [[Node_core_order_status_manager_py]] — Order lifecycle state machine
- [[Node_core_user_manager_py]] — User CRUD + authentication
- [[Node_core_sap_connector_py]] — SAP HANA read-only connector
- [[Node_core_database_client_py]] — SQL Server connection pool
- [[Node_core_relacion_manager_py]] — Relación de envíos management
- [[Node_core_factura_metadata_manager_py]] — Invoice metadata tracking
- [[Node_core_audit_manager_py]] — Audit trail logging
- [[Node_core_print_event_matcher_py]] — Print job ↔ order matching
- [[Node_core_sap_sync_worker_py]] — Background SAP sync thread
- [[Node_core_system_health_py]] — Health check utilities

### Routes (`routes/`)
- [[Node_routes_auth_py]] — Login/logout/password change
- [[Node_routes_orders_py]] — Orders UI + API (3700+ lines)
- [[Node_routes_users_py]] — User management CRUD

### Templates (`templates/`)
- [[Node_templates_base_html]] — Master layout (navbar, sidebar, footer)
- [[Node_templates_orders_index_html]] — Orders list view
- [[Node_templates_orders_monitor_html]] — Real-time TV monitor
- [[Node_templates_orders_facturas_html]] — Invoice management
- [[Node_templates_orders_detail_html]] — Single order detail
- [[Node_templates_orders_dashboard_html]] — Analytics dashboard
- [[Node_templates_orders_visor_html]] — Seller order visor
- [[Node_templates_orders_auditoria_html]] — Audit log viewer
- [[Node_templates_orders_changelog_html]] — Change history
- [[Node_templates_orders_tiempos_tv_html]] — TV time display
- [[Node_templates_orders_tiempos_tv_test_html]] — TV time test
- [[Node_templates_orders_partials__facturas_tab_html]] — Facturas tab partial
- [[Node_templates_orders_partials__relaciones_tab_html]] — Relaciones tab partial
- [[Node_templates_orders_partials__relaciones_history_html]] — Relaciones history
- [[Node_templates_orders_partials__context_menu_html]] — Right-click context menu
- [[Node_templates_orders_partials__relationship_map_modal_html]] — Relationship graph modal
- [[Node_templates_auth_login_html]] — Login page
- [[Node_templates_auth_change_password_html]] — Password change form
- [[Node_templates_users_form_html]] — User create/edit form
- [[Node_templates_users_list_html]] — User list table
- [[Node_templates_errors_404_html]] — 404 error page
- [[Node_templates_errors_500_html]] — 500 error page

### Static Assets (`static/`)
- [[Node_static_js_facturas_js]] — Facturas tab JavaScript logic
- [[Node_static_js_index_js]] — Orders index page JavaScript
- [[Node_static_css_monitor_css]] — Monitor page styles
- [[Node_static_css_facturas_css]] — Facturas tab styles
- [[Node_static_css_design_tokens_css]] — Design system tokens
- [[Node_static_js_alpine_min_js]] — Alpine.js framework
- [[Node_static_js_tailwind_js]] — Tailwind CSS runtime
- [[Node_static_js_Sortable_min_js]] — Drag-and-drop sorting

### Scripts (`scripts/`)
- [[Node_scripts_sync_orders_job_py]] — Scheduled SAP → SQL sync
- [[Node_scripts_sync_print_jobs_job_py]] — Print job sync from SGA
- [[Node_scripts_sync_print_daemon_py]] — Print sync daemon wrapper
- [[Node_scripts_backfill_auto_status_py]] — Historical status backfill
- [[Node_scripts_repair_sync_py]] — Sync repair utility
- [[Node_scripts_reset_admin_py]] — Admin password reset
- [[Node_scripts_audit_sql_py]] — SQL audit script
- [[Node_scripts_audit_json_py]] — JSON audit script
- [[Node_scripts_audit_sga_sao_py]] — SGA↔SAO audit comparison
- [[Node_scripts_openoms_sync_service_py]] — Windows service wrapper

### Middleware
- [[Node_middleware_request_logger_py]] — HTTP request/response logger

### Tests
- [[Node_test_mostrador_py]] — Mostrador (counter) UI tests
- [[Node_test_shipping_py]] — Shipping workflow tests

---

## 📚 Project Documentation
- [[AGENTS]] — AI agent instructions
- [[CODE_OF_CONDUCT]] — Community guidelines
- [[CONTEXT]] — Full system context document
- [[CONTRIBUTING]] — Contribution guide
- [[README]] — Project readme
- [[SECURITY]] — Security policy
- [[README_SYNC]] — Sync service documentation
- [[CI_CD Environment]] — CI/CD pipeline documentation
- [[Open-OMS - Overview]] — System overview
- [[API Endpoints]] — API reference
- [[Application Factory]] — Factory pattern docs
- [[SAP HANA Connector]] — SAP integration docs
- [[System Observintility]] — Observability docs
