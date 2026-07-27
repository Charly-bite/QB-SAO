---
tags:
  - app-core
  - py
  - configuration
---
# ⚙️ config.py

> Multi-environment configuration for Open-OMS.

## Role
Defines configuration classes for `development`, `staging`, `production`, and `testing` environments. Generates a persistent secret key stored in `.flask_secret_key`.

## Configuration Classes
| Class | Environment | Key Settings |
|-------|-------------|-------------|
| `DevelopmentConfig` | Local dev | `DEBUG=True` |
| `StagingConfig` | Pre-prod | `DEBUG=False` |
| `ProductionConfig` | Production | `SECURE cookies`, rotating log handler |
| `TestingConfig` | pytest | CSRF disabled, rate limiter disabled |

## Key Settings
- `PERMANENT_SESSION_LIFETIME`: 8 hours
- `SESSION_COOKIE_NAME`: `sao_session`
- `WTF_CSRF_TIME_LIMIT`: None (no CSRF token expiry)

## Depends On
- `dotenv` — Loads `.env` file
- Standard library only

## Used By
- [[Node_app_py]] — `config_by_name`, `get_config()`
- [[Node_test_mostrador_py]] — `TestingConfig`
- [[Node_test_shipping_py]] — `TestingConfig`

## Part Of
- [[App_Factory]]
