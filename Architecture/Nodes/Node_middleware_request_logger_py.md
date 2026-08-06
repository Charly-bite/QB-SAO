---
tags:
  - middleware
  - py
---
# 📡 middleware/request_logger.py

> **HTTP request/response logger** — logs all requests with timing and user info.

## Role
Flask middleware that measures request duration and logs method, path, status code, and authenticated user on every request.

## Key Function
- `init_request_logger(app)` — Attaches `before_request` and `after_request` hooks

## Depends On
- Flask (`request`, `g`)
- `flask_login` (`current_user`)

## Used By
- [[Node_app_py]] — Initialized in `create_app()`

## Part Of
- [[Middleware]]
