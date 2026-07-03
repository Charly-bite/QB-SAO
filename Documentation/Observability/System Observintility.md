---
tags:
  - open-oms/docs
---
# Observability

The **Observability** layer in Open-OMS ensures that every critical action, error, and system state change is transparent and auditable. This is achieved through structured logging and middleware monitoring.

## 1. Request Logging Middleware

Implemented via `init_request_logger` in the application factory, this component intercepts every incoming HTTP request to capture:
- **Endpoint Visited**: The specific route being accessed.
- **Client Metadata**: IP address, User-Agent, and authentication status.
- **Latency**: Time taken for the server to process and respond to the request.

## 2. Structured Error Handling

The application provides specialized error handlers that distinguish between user-facing errors and system failures:
- **404 Not Found**: Returns a clean HTML error page for browser users, or a JSON error payload for API consumers.
- **500 Internal Server Error**: Captures tracebacks in the logs while presenting a sanitized, non-revealing message to the end user to prevent information leakage.

## 3. Audit Logging

All critical business operations—such as order status updates and administrative logins—are written to the `open_oms.log` file. This creates a permanent, time-stamped trail of system activity, which is essential for security auditing and troubleshooting production issues.

## 4. Health Monitoring

The `/health` endpoint provides a real-time heartbeat of the application's health, reporting on:
- **Application Status**: "OK" or error state.
- **SAP Connectivity**: Whether the `SAPHanaConnector` is currently available and initialized.
- **System Load**: The number of active orders loaded into the `OrderStatusManager`.



---
*Graph Context: Return to [[Home]] (Architecture)*
