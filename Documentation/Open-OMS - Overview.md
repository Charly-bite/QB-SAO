---
tags:
  - open-oms/docs
---
# Open-OMS — Order Tracking Application

The **Open-OMS** application is a specialized tool designed for the real-time monitoring and management of order statuses, primarily integrating with **SAP HANA** to provide visibility into the supply chain.

## Core Purpose
To bridge the gap between SAP backend data and web-based operational tracking, allowing users to monitor order progress through automated status updates.

## System Architecture

The application is built as a modular Flask service:
- [[Core Architecture|Application Core]]: Contains the business logic for user management, authentication, and session handling.
- [[Integrations|External Integrations]]: Handles the heavy lifting of connecting to SAP HANA via specialized connectors.
- [[API & Routes|API Endpoints]]: Provides the interface for both frontend consumption and external monitoring tools.
- [[Observability|System Observability]]: Ensures all transactions, errors, and request flows are logged and auditable.

## Key Technologies
- **Backend**: Python (Flask)
- **Database/ERP**: SAP HANA
- **Security**: Flask-Login, CSRF protection, Rate Limiting
- **Monitoring**: Custom Request Logging Middleware

