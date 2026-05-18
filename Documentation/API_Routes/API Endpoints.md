---
tags:
  - open-oms/docs
---
# API & Routes

The **API & Routes** layer defines the interface through which users and other services interact with Open-OMS. It is organized into distinct Blueprints to separate authentication logic from business operations.

## Routing Structure

### 1. Authentication Blueprint (`auth_bp`)
Handles all identity-related endpoints:
- `GET /login`: Renders the login page.
- `POST /login`: Processes credentials and establishes a session via `Flask-Login`.
- `GET /logout`: Destroys the user session and redirects to login.

### 2. Order Management Blueprint (`orders_bp`)
The primary functional area of the application, prefixed with `/orders`:
- `GET /orders/`: Displays a list of all monitored orders.
- `GET /orders/<order_id>`: Provides detailed views for a specific order.
- `POST /orders/update`: Allows authorized users to manually trigger status changes (if enabled).

## Security & Constraints

To ensure the integrity of the API, several layers of protection are applied:
- **CSRF Protection**: Every `POST` request must include a valid CSR $\text{CSRF}$ token to prevent cross-site attacks.
- **Rate Limiting**: The `flask-limiter` extension prevents automated scraping or brute-force attempts on the `/login` and `/orders/update` endpoints.
- **Session Expiration**: A custom error handler manages expired sessions by clearing the CSRF token and redirecting users to re-authenticate.

## API Responses
For programmatic access, the application provides JSON responses for any request containing `application/json` headers, returning structured errors or data payloads.

