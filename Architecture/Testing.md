# 🧪 Testing

> Unit and integration tests for the Open-OMS application.

## Test Files

| Test | File | What It Tests | Dependencies |
|------|------|---------------|--------------|
| **Mostrador Tests** | [[Node_test_mostrador_py]] | Counter/monitor UI behavior | [[Node_app_py]], [[Node_core_order_status_manager_py]] |
| **Shipping Tests** | [[Node_test_shipping_py]] | Shipping workflow, status transitions | [[Node_app_py]], [[Node_core_order_status_manager_py]] |

## Test Configuration
- Uses `TestingConfig` from [[Node_config_py]]:
  - `TESTING = True`
  - `WTF_CSRF_ENABLED = False` (no CSRF in tests)
  - `RATELIMIT_ENABLED = False` (no rate limiting)
  - `SECRET_KEY = 'test-secret-key-not-for-production'`
  - `SERVER_NAME = 'localhost.test'`

## Load Testing
- [[Node_locustfile_py]] — General load test scenarios
- [[Node_monitor_locustfile_py]] — Monitor-specific load testing

## Running Tests
```bash
scripts/run_tests.bat
# or directly:
pytest --cov=. --cov-report=term-missing
```

---
*Part of [[Home]] architecture*
