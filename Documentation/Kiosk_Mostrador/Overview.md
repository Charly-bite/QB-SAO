---
tags:
  - open-oms/docs
  - kiosk
  - mostrador
---

# Kiosk & Mostrador Isolation Environment

This documentation details the architecture, routing, and filtering rules for the **Kiosk screen** and the specialized **Mostrador** user in Open-OMS. 

The Kiosk system is designed as an isolated environment so that custom visual/functional changes requested for the customer-facing display do not impact internal monitors used by Sellers, Admins, or Operators.

---

## 1. Context & Use Case

- **Mostrador User**: The user account with the username `mostrador` (case-insensitive) is dedicated to running a customer-facing screen Kiosk.
- **Kiosk Display**: A physical TV or monitor running in the store where customers scan a code or check the screen to view the status of their counter-pickup orders in real-time.
- **Goal of Isolation**: Any customization to the Kiosk's theme, layout, audio announcements, or columns must be contained *strictly* within the Mostrador views, without altering the default order monitors used by company employees.

---

## 2. File Architecture

The isolation is achieved by separating template files and routing paths:

| File / Component | Path | Description |
| :--- | :--- | :--- |
| **Mostrador Template** | `templates/orders/monitor_mostrador.html` | **Exclusive customer-facing view** for the Kiosk screen. Includes audio announcements, special visual designs, and recent status change history. |
| **Standard Monitor Template** | `templates/orders/monitor.html` | General monitor for sellers, operators, managers, and administrators. |
| **Startup Script** | `launch_kiosk.bat` | Windows batch file to boot the system in Kiosk mode. |

---

## 3. Routing & Redirection Rules

The system intercepts requests for the `mostrador` and `monitor` users to force them into the Kiosk monitor view:

### A. Login Redirection
In `routes/auth.py#L30-L31` and `routes/auth.py#L66-L67`, if a user logs in and their username is `"mostrador"` or `"monitor"`, they are redirected directly to the `/orders/monitor` route:
```python
if current_user.username.lower() in ["mostrador", "monitor"]:
    return redirect(url_for("orders.monitor"))
```

### B. Dashboard Index Redirection
In `routes/orders.py#L380-L381`, if a user attempts to access the main order dashboard index `/orders/`, they are redirected to `/orders/monitor`:
```python
if getattr(current_user, "username", "").lower() in ["mostrador", "monitor"]:
    return redirect(url_for("orders.monitor"))
```

### C. Monitor View Selection
In `routes/orders.py#L1663-L1670`, the `/orders/monitor` route decides which template to load based on the logged-in user:
```python
@orders_bp.route("/monitor")
@login_required
def monitor():
    if current_user.username.lower() == 'mostrador':
        return render_template("orders/monitor_mostrador.html", now=datetime.datetime.now())
    return render_template("orders/monitor.html", now=datetime.datetime.now())
```

---

## 4. Data Filtering Rules (Scoped View)

Since the Kiosk is placed in the store, it must only show over-the-counter orders. 

In `routes/orders.py` (under endpoints `/api/active` and `/api/seller/orders`), the list of orders is filtered for the `"mostrador"` user:
```python
if getattr(current_user, "username", "").lower() == "mostrador":
    # Mostrador user sees only orders with shipping_type = VENTA MOSTRADOR
    active_orders = [
        o for o in active_orders
        if o.get("shipping_type", "").upper().strip() in [
            "VENTA MOSTRADOR", "VENTA DE MOSTRADOR", "VENTAS MOSTRADOR"
        ] or "VENTAS MOSTRADOR" in str(o.get("customer_name", "")).upper()
    ]
```

---

## 5. UI Features & Differences

### A. Historial Reciente (Recent History Panel)
- **`monitor_mostrador.html`**: The sidebar "Historial Reciente" is **always visible and open**, even if there are no recent updates. If empty, it displays `"Sin pedidos recientes"`.
- **`monitor.html`**: The sidebar is conditionally rendered. It is only shown if the user is `mostrador` AND there is at least one item in `historyOrders`.

### B. Audio Announcements & Speech
- The Mostrador view features Web Speech API integration that verbally announces order state transitions in Spanish (e.g., *"Pedido 12345 en proceso"* or *"Pedido 12345 listo para entrega"*).
- Features a Test Audio button exclusive to the Kiosk layout to verify text-to-speech speaker volume.

### C. Visual Enhancements
- Includes full-screen TV transitions and background animation gradients (`mostrador-gradient`) tailored to public-facing displays.

---

## 6. Startup Script (`launch_kiosk.bat`)

The Kiosk is launched locally in the physical store using the `launch_kiosk.bat` batch file. This script starts Google Chrome (or Microsoft Edge) in `--kiosk` full-screen mode pointing to the monitor URL and bypasses browser user-gesture restrictions for media playback so voice announcements can auto-play:

```batch
start chrome --kiosk "http://<IP_ADDRESS>:5009/orders/monitor" --autoplay-policy=no-user-gesture-required
```
