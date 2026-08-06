# 📡 Middleware

> `middleware/` — Request/response processing layers.

## Request Logger — [[Node_middleware_request_logger_py]]

Initialized in [[App_Factory]] via `init_request_logger(app)`.

### What It Does
- Logs every HTTP request with timing, user, method, path, and status code
- Uses Flask's `before_request` and `after_request` hooks
- Measures request duration via `flask.g`
- Identifies authenticated users via `flask_login.current_user`

### Log Format
```
[INFO] 192.168.2.100 | admin | GET /orders/monitor | 200 | 45ms
```

### Connections
- **Initialized by**: [[Node_app_py]] (in `create_app()`)
- **Uses**: Flask's `request`, `g`, and `flask_login.current_user`
- **Logs to**: `logs/open_oms.log`

---
*Part of [[Home]] architecture*
