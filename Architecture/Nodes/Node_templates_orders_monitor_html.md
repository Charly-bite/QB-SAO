---
tags:
  - template
  - html
  - orders
  - monitor
---
# 📺 templates/orders/monitor.html

> **Real-time TV monitor** — the largest template (~93KB). Displays orders on warehouse/office TVs.

## Role
Full-screen real-time order monitor with SSE updates, audio notifications, weather display, and drag-and-drop reordering. Used by "mostrador" and "monitor" users.

## Extends
- [[Node_templates_base_html]]

## Includes (Partials)
- [[Node_templates_orders_partials__facturas_tab_html]] — Facturas tab
- [[Node_templates_orders_partials__relaciones_tab_html]] — Relaciones tab
- [[Node_templates_orders_partials__context_menu_html]] — Right-click menu
- [[Node_templates_orders_partials__relationship_map_modal_html]] — Relationship graph modal

## Static Assets
- [[Node_static_css_monitor_css]] — Monitor-specific styles
- [[Node_static_js_Sortable_min_js]] — Drag-and-drop
- [[Node_static_js_alpine_min_js]] — Reactivity
- Audio notification files (announcement sounds)

## Served By
- [[Node_routes_orders_py]] — `GET /orders/monitor`

## Features
- SSE real-time streaming from [[Node_routes_orders_py]]
- Audio notifications for new orders
- Weather widget
- Historial Reciente (mostrador user only)
- Checkbox persistence for "Relación de envío"
- Color-coded status rows

## Part Of
- [[Frontend]], [[Routes]]
