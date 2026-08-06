---
name: Kiosk and Mostrador isolated environment
description: Context and guidelines for working with the Kiosk screen, the specialized Mostrador user, and their isolated templates and routing logic.
---

# Kiosk & Mostrador Isolation Environment

Use this skill when modifying, debugging, or extending the order status kiosk or the specialized `Mostrador` user. 

## Key Architecture

### 1. Isolated View File
- Customer-facing screen display: [monitor_mostrador.html](file:///c:/Users/CarlosAlbertoAcevesC/Desktop/DEV%20SAO/templates/orders/monitor_mostrador.html)
- Standard employee/seller monitor: [monitor.html](file:///c:/Users/CarlosAlbertoAcevesC/Desktop/DEV%20SAO/templates/orders/monitor.html)
- **CRITICAL**: Never add features meant for the Kiosk to `monitor.html` unless requested. Keep all Kiosk logic inside `monitor_mostrador.html` to prevent regressions for standard users.

### 2. Auto-redirection & Routing
- Enforced redirects for username `mostrador` (case-insensitive) are located in:
  - [routes/auth.py](file:///c:/Users/CarlosAlbertoAcevesC/Desktop/DEV%20SAO/routes/auth.py) (Redirects logins to `/orders/monitor`)
  - [routes/orders.py](file:///c:/Users/CarlosAlbertoAcevesC/Desktop/DEV%20SAO/routes/orders.py) (Redirects `/orders/` to `/orders/monitor`, and chooses `monitor_mostrador.html` template)

### 3. Data Scoping & Filtering
- Endpoints `/api/active` and `/api/seller/orders` in [routes/orders.py](file:///c:/Users/CarlosAlbertoAcevesC/Desktop/DEV%20SAO/routes/orders.py) filter active orders for `mostrador`:
  - Shows only orders where `shipping_type` is one of `["VENTA MOSTRADOR", "VENTA DE MOSTRADOR", "VENTAS MOSTRADOR"]` or where `customer_name` contains `"VENTAS MOSTRADOR"`.

### 4. Distinct Features
- **Historial Reciente**: In `monitor_mostrador.html`, this sidebar is permanently open/rendered, showing `"Sin pedidos recientes"` if empty.
- **Audio Announcements**: Verbally speaks status updates in Spanish and offers an audio-test button on screen.
- **Screen Rotation**: Visual styling specifically suited for full-screen kiosks.
