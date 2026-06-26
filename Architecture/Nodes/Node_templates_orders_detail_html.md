---
tags:
  - template
  - html
  - orders
---
# 🔍 templates/orders/detail.html

> **Single order detail view** — shows full order information.

## Extends
- [[Node_templates_base_html]]

## Served By
- [[Node_routes_orders_py]] — `GET /orders/<order_id>`

## Displays
- Order header (customer, seller, dates, status)
- Order line items (from SAP via [[Node_core_sap_connector_py]])
- Status history timeline
- Action buttons (role-dependent via [[Node_models_py]])

## Part Of
- [[Frontend]]
