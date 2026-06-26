---
tags:
  - open-oms/docs
---
# Core Architecture

The **Core Architecture** of Open-OMS is built around a modular "Application Factory" pattern using Flask. This ensures that the application remains testable, scalable, and decoupled from its environment.

## Key Components

### 1. Application Factory (`create_app`)
The central entry point that initializes the Flask instance, configures extensions (like SQLAlchemy or CSRFProtect), and registers all blueprints.

### 2. User Management (`core/user_manager.py`)
Handles user authentication, session management via `Flask-Login`, and role-based access control (RB $\text{RBAC}$). It manages:
- **User Loading**: Authenticating users based on stored credentials.
- **Role Assignment**: Defining permissions for different levels of access (e.g., Admin vs. Viewer).

### 3. Order Status Management (`core/order_status_manager.py`)
The business logic engine that processes order transitions. It is responsible for:
- **State Transitions**: Moving orders through lifecycle stages (e.g., `Pending` $\rightarrow$ `Processing` $\rightarrow$ `Shipped`).
- **Data Aggregation**: Collecting data from the SAP connector to present a unified view of each order.

## Integration with Flask Extensions
The architecture heavily leverages:
- **Flask-Login**: For secure session handling and `@login_required` decorators.
- **Flask-WTF**: To provide robust CSRF protection across all form submissions.
- **Flask-Limiter**: To protect the application from brute-force attacks and DoS attempts via rate limiting.



---
*Graph Context: Return to [[Home]] (Architecture)*
