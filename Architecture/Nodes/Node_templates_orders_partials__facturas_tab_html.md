---
tags:
  - template
  - html
  - partial
  - facturas
---
# 🧾 templates/orders/partials/_facturas_tab.html

> **Facturas tab partial** — reusable invoice management tab embedded in the monitor.

## Role
A self-contained tab component showing invoice metadata, daily order tracking, and factura editing controls. Included inside [[Node_templates_orders_monitor_html]].

## Static Assets
- [[Node_static_js_facturas_js]] — Client-side logic
- [[Node_static_css_facturas_css]] — Styles

## Included By
- [[Node_templates_orders_monitor_html]] — `{% include %}` directive

## Related
- [[Node_core_factura_metadata_manager_py]] — Backend data
- [[Node_templates_orders_facturas_html]] — Standalone version

## Part Of
- [[Frontend]]
