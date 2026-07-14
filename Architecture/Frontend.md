# 🎨 Frontend UI

> `templates/` + `static/` — Jinja2 templates with Tailwind CSS and Alpine.js.

## Technology Stack
- **Templating**: Jinja2 (Flask)
- **CSS Framework**: Tailwind CSS via [[Node_static_js_tailwind_js]]
- **Reactivity**: Alpine.js via [[Node_static_js_alpine_min_js]]
- **Drag & Drop**: Sortable.js via [[Node_static_js_Sortable_min_js]]
- **Design System**: Custom tokens in [[Node_static_css_design_tokens_css]]

## Template Hierarchy

```
base.html (master layout)
    ├── orders/index.html (order list)
    ├── orders/monitor.html (TV monitor)
    │       ├── partials/_facturas_tab.html
    │       ├── partials/_relaciones_tab.html
    │       │       └── partials/_relaciones_history.html
    │       ├── partials/_context_menu.html
    │       └── partials/_relationship_map_modal.html
    ├── orders/facturas.html (invoice mgmt)
    ├── orders/detail.html (order detail)
    ├── orders/dashboard.html (analytics)
    ├── orders/visor.html (seller view)
    ├── orders/auditoria.html (audit log)
    ├── orders/changelog.html (changes)
    ├── orders/tiempos_tv.html (TV times)
    ├── auth/login.html (login page)
    ├── auth/change_password.html
    ├── users/list.html (user list)
    ├── users/form.html (user form)
    └── errors/
            ├── 404.html
            └── 500.html
```

## CSS Files
| File | Scope | Used By |
|------|-------|---------|
| [[Node_static_css_monitor_css]] | Monitor page styles | [[Node_templates_orders_monitor_html]] |
| [[Node_static_css_facturas_css]] | Facturas tab & page | [[Node_templates_orders_facturas_html]], [[Node_templates_orders_partials__facturas_tab_html]] |
| [[Node_static_css_design_tokens_css]] | Global design tokens | All templates via [[Node_templates_base_html]] |
| Tailwind CSS | Utility classes | All templates |

## JavaScript Files
| File | Scope | Used By |
|------|-------|---------|
| [[Node_static_js_facturas_js]] | Facturas tab logic | [[Node_templates_orders_facturas_html]], [[Node_templates_orders_partials__facturas_tab_html]] |
| [[Node_static_js_index_js]] | Orders index logic | [[Node_templates_orders_index_html]] |
| [[Node_static_js_alpine_min_js]] | Reactivity framework | All interactive templates |
| [[Node_static_js_tailwind_js]] | CSS framework | All templates |
| [[Node_static_js_Sortable_min_js]] | Drag-and-drop sorting | [[Node_templates_orders_monitor_html]] |

## Template ↔ Route Mapping
See [[Routes]] for the complete route → template mapping.

---
*Part of [[Home]] architecture*
