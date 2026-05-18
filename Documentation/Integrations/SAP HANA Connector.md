---
tags:
  - open-oms/docs
---
# Integrations

The **Integrations** layer is responsible for connecting the Open-OMS application to external enterprise systems, most notably **SAP HANA**. This allows the application to act as a real-time window into the broader corporate ecosystem.

## SAP HANA Connector

The core of this integration is the `SAPHanaConnector` (located in `core/sap_connector.py`). It facilitates:
- **Lazy Connection**: Establishing connections only when required to save resources.
- **Data Retrieval**: Querying complex HANA schemas for order-specific details, delivery dates, and client information.
- **Schema Management**: Interfacing with the `SBO_QUIMICABOSS` schema to fetch live business data.

## Technical Requirements
For this integration to function, the environment must include:
- **hdbcli**: The official SAP HANA Python driver.
- **Environment Variables**: Configuration for `SAP_HOST`, `SAP_PORT`, `SAP_USER`, and `SAP_PASS`.

## Error Handling & Resiliency
The connector is designed with failure-aware logic:
- If the connection fails, the application gracefully falls back to "Standalone Mode," where it relies on cached or local data.
- The `app.py` factory includes checks (`SAP_AVAILABLE`) to prevent application crashes during startup if the HANA driver is missing.

