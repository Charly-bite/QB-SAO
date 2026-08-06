---
tags:
  - template
  - html
  - orders
---
# 📋 templates/orders/index.html

> **Orders list view** — the main dashboard showing all tracked orders.

## Role
Displays a filterable, sortable table of all orders with status badges, seller info, and action buttons. Supports role-based visibility.

## Extends
- [[Node_templates_base_html]]

## Static Assets
- [[Node_static_js_index_js]] — Client-side filtering, sorting, checkbox persistence
- [[Node_static_css_design_tokens_css]] — Design tokens

## Served By
- [[Node_routes_orders_py]] — `GET /orders/`

## Part Of
- [[Frontend]], [[Routes]]
