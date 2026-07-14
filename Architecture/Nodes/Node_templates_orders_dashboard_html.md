---
tags:
  - template
  - html
  - orders
  - analytics
---
# 📊 templates/orders/dashboard.html

> **Analytics dashboard** — charts and metrics for order performance.

## Extends
- [[Node_templates_base_html]]

## Served By
- [[Node_routes_orders_py]] — `GET /orders/dashboard`

## Access
- Requires `can_view_dashboard()`: ADMIN, VIEWER roles only (via [[Node_models_py]])

## Part Of
- [[Frontend]]
