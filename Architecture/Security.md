# 🔒 Security

> Security layers applied across the Open-OMS application.

## Authentication & Authorization

| Layer | Implementation | File |
|-------|---------------|------|
| **Login/Logout** | Flask-Login session management | [[Node_routes_auth_py]] |
| **User Model** | `User` class with role-based permissions | [[Node_models_py]] |
| **Password Hashing** | `werkzeug.security` (bcrypt-based) | [[Node_core_user_manager_py]] |
| **Role System** | `UserRole` enum: ADMIN, OPERATOR, VIEWER, SELLER, SELL_MANAGER, BILLING | [[Node_core_user_manager_py]] |

## Role Permissions Matrix

| Permission | ADMIN | OPERATOR | SELL_MANAGER | BILLING | SELLER | VIEWER |
|------------|:-----:|:--------:|:------------:|:-------:|:------:|:------:|
| View all orders | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Edit orders | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Print labels | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit facturas | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Manage users | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View dashboard | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Sign facturación | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Sign almacén | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

## CSRF Protection
- Global CSRF via `Flask-WTF` CSRFProtect — [[Node_app_py]]
- Graceful CSRF expiry → redirect to login instead of 400 error
- **Exempt**: SGA webhook endpoint (`sga_label_printed`) — machine-to-machine

## Rate Limiting
- Global: `500/min`, `20/sec` via [[Node_extensions_py]]
- Login: `5/min` on POST — [[Node_routes_auth_py]]

## Session Security
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = 'Lax'`
- `SESSION_COOKIE_SECURE = True` (production)
- 8-hour session lifetime
- Custom cookie name `sao_session` to avoid collision with SGA

---
*Part of [[Home]] architecture*
