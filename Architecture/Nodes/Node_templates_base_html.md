---
tags:
  - template
  - html
  - layout
---
# 🏗️ templates/base.html

> **Master layout template** — all pages extend this.

## Role
Defines the HTML skeleton: `<head>`, navbar, sidebar, flash messages, footer, and common scripts. Every other template uses `{% extends "base.html" %}`.

## Includes
- [[Node_static_js_tailwind_js]] — Tailwind CSS
- [[Node_static_js_alpine_min_js]] — Alpine.js
- [[Node_static_css_design_tokens_css]] — Design system tokens
- Navbar with role-based menu items (uses `current_user` from [[Node_models_py]])

## Extended By
- [[Node_templates_orders_index_html]]
- [[Node_templates_orders_monitor_html]]
- [[Node_templates_orders_facturas_html]]
- [[Node_templates_orders_detail_html]]
- [[Node_templates_orders_dashboard_html]]
- [[Node_templates_orders_visor_html]]
- [[Node_templates_orders_auditoria_html]]
- [[Node_templates_orders_changelog_html]]
- [[Node_templates_orders_tiempos_tv_html]]
- [[Node_templates_auth_login_html]]
- [[Node_templates_auth_change_password_html]]
- [[Node_templates_users_list_html]]
- [[Node_templates_users_form_html]]
- [[Node_templates_errors_404_html]]
- [[Node_templates_errors_500_html]]

## Part Of
- [[Frontend]]
