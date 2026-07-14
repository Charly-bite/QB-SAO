---
tags:
  - template
  - html
  - users
---
# 📋 templates/users/list.html

> **User list table** — displays all system users with status.

## Extends
- [[Node_templates_base_html]]

## Served By
- [[Node_routes_users_py]] — `GET /users/`

## Features
- Online status indicator (green dot if active < 15 min)
- Last login timestamp
- Role badges
- Edit/delete actions (admin only)

## Part Of
- [[Frontend]]
