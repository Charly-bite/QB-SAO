---
tags:
  - template
  - html
  - users
---
# ✏️ templates/users/form.html

> **User create/edit form** — shared form for creating and editing user accounts.

## Extends
- [[Node_templates_base_html]]

## Served By
- [[Node_routes_users_py]] — `GET/POST /users/create` and `/users/<id>/edit`

## Fields
- Username, full name, email
- Role selector (UserRole enum from [[Node_core_user_manager_py]])
- Warehouse, SAP seller name
- Password (create) / reset password (edit)

## Part Of
- [[Frontend]]
