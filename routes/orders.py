"""
Order status routes for SGA Web
"""

import datetime
import json as json_mod
import logging
import os
import threading
import time
import urllib.request
from functools import wraps

import io
from flask import Blueprint, current_app, jsonify, render_template, request, Response, send_file, url_for
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import queue
from flask_login import current_user, login_required

from core.order_status_manager import OrderStatus

# Weather cache (module-level)
_weather_cache = {"data": None, "timestamp": 0}

orders_bp = Blueprint("orders", __name__)

# Simple in-memory pub/sub for Server-Sent Events (SSE)
_SUBSCRIBERS = []

# ── Webhook retry queue ──────────────────────────────────────────────────────
# When SGA fires a label-printed webhook for an order that isn't loaded yet,
# we enqueue it here and retry every 30 s (up to MAX_RETRIES attempts).
_WEBHOOK_RETRY_QUEUE: list = []   # list of retry-entry dicts
_RETRY_LOCK = threading.Lock()
_WEBHOOK_MAX_RETRIES = 3
_WEBHOOK_RETRY_INTERVAL = 30      # seconds between attempts


def _publish_event(event: dict):
    # Push event to all subscriber queues (non-blocking)
    for q in list(_SUBSCRIBERS):
        try:
            q.put(event, block=False)
        except queue.Full:
            pass
        except Exception as e:  # pragma: no cover
            current_app.logger.warning(f"Error publishing event: {e}")


def _webhook_retry_worker(app):  # pragma: no cover
    """Background daemon that retries failed label-printed webhooks.

    Runs every _WEBHOOK_RETRY_INTERVAL seconds inside the Flask app context.
    On each cycle it drains _WEBHOOK_RETRY_QUEUE, attempts the SAP import +
    status update, and either resolves or re-queues the entry (up to
    _WEBHOOK_MAX_RETRIES times).
    """
    import time as _time
    with app.app_context():
        while True:
            _time.sleep(_WEBHOOK_RETRY_INTERVAL)
            with _RETRY_LOCK:
                pending = list(_WEBHOOK_RETRY_QUEUE)
                _WEBHOOK_RETRY_QUEUE.clear()

            still_pending = []
            for entry in pending:
                order_id = entry["order_id"]
                station  = entry["station"]
                data     = entry["data"]
                attempt  = entry["attempt"] + 1

                order_mgr = app.order_status_mgr
                order = order_mgr.get_order(order_id)

                if not order and app.sap_available and app.sap_connector:
                    try:
                        sap = app.sap_connector
                        if not sap.connected:
                            sap.connect()
                        order_data = sap.get_order_details(order_id)
                        if order_data:
                            h = order_data.get("header", {})
                            flat = {
                                "DocNum":          h.get("order_number"),
                                "DocEntry":        h.get("doc_entry"),
                                "CardCode":        h.get("customer_code"),
                                "CardName":        h.get("customer_name"),
                                "DocDate":         h.get("order_date"),
                                "DocDueDate":      h.get("delivery_date"),
                                "DocTotal":        h.get("total_value", 0),
                                "DocCurrency":     h.get("currency", "MXN"),
                                "Comments":        "",
                                "items":           order_data.get("items", []),
                                "sap_status":      h.get("sap_status", "Abierto"),
                                "factura_number":  h.get("factura_number"),
                                "delivery_number": h.get("delivery_number"),
                                "updated_by":      h.get("updater_name", "SGA Webhook"),
                                "created_by":      h.get("creator_name"),
                                "creator_name":    h.get("creator_name"),
                            }
                            sap_user = h.get("updater_name", "SGA Webhook")
                            order = order_mgr.import_from_sap(flat, imported_by=sap_user)
                            logging.info(
                                f"[Retry {attempt}/{_WEBHOOK_MAX_RETRIES}] "
                                f"Order {order_id} auto-imported from SAP."
                            )
                    except Exception as e:
                        logging.warning(
                            f"[Retry {attempt}/{_WEBHOOK_MAX_RETRIES}] "
                            f"SAP import for order {order_id} failed: {e}"
                        )

                if order:
                    # Order is now available — apply the transition
                    current_status = order.get("status", "")
                    target_status  = OrderStatus.IN_PROGRESS.value
                    if current_status not in _MAIN_STATUSES or \
                            _MAIN_STATUSES.index(current_status) <= \
                            _MAIN_STATUSES.index(target_status):
                        items      = data.get("items", [])
                        event_type = data.get("event_type", "DIRECT_PRINT_JOB")
                        notes = f"Impresion SGA (station={station}, type={event_type}, retry={attempt}"
                        if items:
                            notes += f", items={sorted(items)}"
                        notes += ")"
                        success = order_mgr.update_status(
                            order_id, target_status, station, notes=notes
                        )
                        if success:
                            logging.info(
                                f"[Retry {attempt}] SGA webhook resolved: "
                                f"order={order_id} -> {target_status}"
                            )
                            try:
                                updated_order = order_mgr.get_order(order_id)
                                _publish_event({
                                    "type": "order_updated",
                                    "order_id": str(order_id),
                                    "order": updated_order,
                                })
                                _publish_event({
                                    "type": "status_changed",
                                    "order_id": str(order_id),
                                    "from": current_status,
                                    "to": target_status,
                                    "customer": updated_order.get("customer_name", "") if updated_order else "",
                                })
                            except Exception:  # pragma: no cover
                                pass  # pragma: no cover
                        else:
                            logging.warning(
                                f"[Retry {attempt}] status update failed for order {order_id}"
                            )
                    # Either resolved or already at higher status — don't re-queue
                elif attempt < _WEBHOOK_MAX_RETRIES:
                    entry["attempt"] = attempt
                    still_pending.append(entry)
                    logging.warning(
                        f"[Retry {attempt}/{_WEBHOOK_MAX_RETRIES}] "
                        f"Order {order_id} still not available — will retry."
                    )
                else:
                    logging.error(
                        f"[Retry FINAL] Giving up on webhook for order {order_id} "
                        f"after {_WEBHOOK_MAX_RETRIES} attempts (station={station})."
                    )
                    # DLQ Implementation
                    try:
                        if app.order_status_mgr.sql_engine:
                            with app.order_status_mgr.sql_engine.begin() as conn:
                                # Ensure table exists
                                conn.exec_driver_sql("""
                                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_webhook_dlq' and xtype='U')
                                    CREATE TABLE seguimiento_webhook_dlq (
                                        id INT IDENTITY(1,1) PRIMARY KEY,
                                        order_id VARCHAR(50),
                                        station VARCHAR(100),
                                        payload NVARCHAR(MAX),
                                        failed_at DATETIME DEFAULT GETDATE()
                                    )
                                """)
                                import json
                                conn.exec_driver_sql(
                                    "INSERT INTO seguimiento_webhook_dlq (order_id, station, payload) VALUES (?, ?, ?)",
                                    (order_id, station, json.dumps(entry))
                                )
                                logging.info(f"💾 Webhook for order {order_id} saved to Dead-Letter Queue (seguimiento_webhook_dlq)")
                    except Exception as dlq_err:
                        logging.error(f"Failed to save webhook to DLQ: {dlq_err}")

            if still_pending:
                with _RETRY_LOCK:
                    _WEBHOOK_RETRY_QUEUE.extend(still_pending)


def init_webhook_retry(app):  # pragma: no cover
    """Start the webhook retry background daemon.  Call once after create_app()."""
    t = threading.Thread(
        target=_webhook_retry_worker,
        args=(app,),
        name="webhook-retry",
        daemon=True,
    )
    t.start()
    logging.info("Webhook retry worker started (interval=%ds, max_retries=%d)",
                 _WEBHOOK_RETRY_INTERVAL, _WEBHOOK_MAX_RETRIES)


def _require_monitor_token(f):
    """Decorator that checks for a valid monitor token on public endpoints.
    If MONITOR_TOKEN is not set in the environment, access is open (backward-compat)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        expected = os.environ.get("MONITOR_TOKEN", "")
        if expected:
            token = request.headers.get("X-Monitor-Token") or request.args.get(
                "token", ""
            )
            if token != expected:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def _require_sga_api_key(f):
    """Decorator for SGA machine-to-machine endpoints.
    Requires SGA_API_KEY to be set in the environment; if not set the endpoint
    is disabled (503) to prevent accidental open access."""

    @wraps(f)
    def decorated(*args, **kwargs):
        expected = os.environ.get("SGA_API_KEY", "")
        if not expected:
            return jsonify({"error": "SGA API not configured"}), 503
        token = request.headers.get("X-API-Key") or request.args.get(
            "api_key", ""
        )
        if token != expected:
            # Log enough detail to identify the misconfigured station
            masked = (token[:4] + "****") if token else "<missing>"
            logging.warning(
                "SGA API key rejected — ip=%s, token_prefix='%s', endpoint=%s",
                request.remote_addr, masked, request.path,
            )
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def _check_delivery_and_invoice(sap, order_mgr, recent_orders):  # pragma: no cover
    """Auto-transition orders based on SAP delivery notes and invoices.

    Called inside the SAP sync cycle.  Uses the already-fetched ``recent_orders``
    to collect ``doc_entry`` values, then batch-queries ODLN and OINV.

    Transitions:
      - En Proceso / Pendiente  + delivery note → Entregado
      - Entregado               + invoice       → Facturacion

    Returns the number of orders whose status was updated.
    """
    # Build doc_entry → order_id map from the recent SAP fetch
    entry_to_oid = {}  # doc_entry → order_id string
    for order_data in recent_orders:
        if not order_data or "header" not in order_data:
            continue
        header = order_data["header"]
        doc_entry = header.get("doc_entry")
        order_id = str(header.get("order_number", ""))
        if doc_entry and order_id and order_id in order_mgr.orders:
            entry_to_oid[int(doc_entry)] = order_id
            # Persist doc_entry on the local order for future lookups
            order_mgr.orders[order_id]["doc_entry"] = int(doc_entry)

    # Also include older local orders that have a stored doc_entry and
    # are still at a status eligible for auto-transition.  This catches
    # orders that fell outside the recent-50 SAP window.
    _eligible_statuses = {
        OrderStatus.PENDING.value,
        OrderStatus.IN_PROGRESS.value,
        OrderStatus.PICKING.value,  # Entregado — eligible for Facturacion
    }
    for oid, order in order_mgr.orders.items():
        if oid in entry_to_oid.values():
            continue  # already covered by recent SAP fetch
        de = order.get("doc_entry")
        if de and order.get("status") in _eligible_statuses:
            entry_to_oid[int(de)] = oid

    if not entry_to_oid:
        return 0

    updated = 0

    # ── 1. Delivery Notes → Entregado ────────────────────────────────
    # Only check orders that are still at Pendiente or En Proceso
    eligible_for_terminado = {
        de: oid for de, oid in entry_to_oid.items()
        if order_mgr.orders[oid].get("status") in [
            OrderStatus.PENDING.value,
            OrderStatus.IN_PROGRESS.value,
        ]
    }

    if eligible_for_terminado:
        deliveries = sap.get_delivery_notes_batch(list(eligible_for_terminado.keys()))
        for de, delivery_info in deliveries.items():
            oid = eligible_for_terminado.get(de)
            if not oid:
                continue
            dn = delivery_info["delivery_num"]
            order_mgr.orders[oid]["delivery_number"] = str(dn)
            order_mgr.update_status(
                oid,
                OrderStatus.PICKING.value,  # "Entregado"
                "system",
                notes=f"Auto: Nota de entrega #{dn} detectada en SAP",
            )
            logging.info(
                f"Auto-Entregado: order={oid}, delivery_note={dn}"
            )
            # Broadcast SSE
            try:
                _publish_event({
                    "type": "order_updated",
                    "order_id": oid,
                    "order": order_mgr.get_order(oid),
                })
            except Exception as e:
                current_app.logger.warning(f"Ignored exception: {e}")
            updated += 1

    # ── 2. Invoices → Facturacion ─────────────────────────────────────
    # Check orders at Entregado (including those just transitioned above)
    eligible_for_factura = {
        de: oid for de, oid in entry_to_oid.items()
        if order_mgr.orders[oid].get("status") == OrderStatus.PICKING.value
        and not order_mgr.orders[oid].get("factura_number")
    }

    if eligible_for_factura:
        invoices = sap.get_invoices_for_orders_batch(list(eligible_for_factura.keys()))
        for de, invoice_num in invoices.items():
            oid = eligible_for_factura.get(de)
            if not oid:
                continue
            order_mgr.orders[oid]["factura_number"] = str(invoice_num)
            order_mgr.update_status(
                oid,
                OrderStatus.INVOICING.value,  # "Facturacion"
                "system",
                notes=f"Auto: Factura #{invoice_num} detectada en SAP",
            )
            logging.info(
                f"Auto-Facturacion: order={oid}, invoice={invoice_num}"
            )
            try:
                _publish_event({
                    "type": "order_updated",
                    "order_id": oid,
                    "order": order_mgr.get_order(oid),
                })
            except Exception as e:
                current_app.logger.warning(f"Ignored exception: {e}")
            updated += 1

    return updated


@orders_bp.route("/")
@login_required
def index():
    """Order status dashboard"""
    order_mgr = current_app.order_status_mgr

    # Get filter params
    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    # Get all orders (filtering is now handled client-side via Alpine.js)
    orders = list(order_mgr.orders.values())

    # Sort by order_id (DocNum) descending - newest orders first
    # Convert order_id to int for proper numeric sorting
    orders.sort(
        key=lambda x: (
            int(x.get("order_id", 0)) if str(x.get("order_id", "")).isdigit() else 0
        ),
        reverse=True,
    )

    # Get status counts
    status_counts = {}
    for status in OrderStatus:
        count = len(
            [o for o in order_mgr.orders.values() if o.get("status") == status.value]
        )
        status_counts[status.value] = count

    return render_template(
        "orders/index.html",
        orders=orders,
        status_filter=status_filter,
        search=search,
        status_counts=status_counts,
        OrderStatus=OrderStatus,
    )


@orders_bp.route("/changelog")  # pragma: no cover
@login_required
def changelog():
    """Version history and changelog"""
    import json
    import os
    changelog_path = os.path.join(current_app.root_path, 'changelog.json')
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            changes = json.load(f)
    except Exception:
        changes = []
    return render_template("orders/changelog.html", changelog=changes)


@orders_bp.route('/stream')
@_require_monitor_token
def stream():
    """Server-Sent Events stream that broadcasts order updates to monitors.

    Sends a ':keepalive' comment every 25 s so the connection is never idle
    long enough for a proxy or browser to drop it.
    """
    q = queue.Queue()
    _SUBSCRIBERS.append(q)

    def event_stream(local_q):  # pragma: no cover
        try:  # pragma: no cover
            while True:  # pragma: no cover
                try:  # pragma: no cover
                    data = local_q.get(timeout=25)  # pragma: no cover
                    yield f"data: {json_mod.dumps(data, ensure_ascii=False)}\n\n"  # pragma: no cover
                except queue.Empty:  # pragma: no cover
                    # No event in 25 s — send a keepalive comment so the
                    # connection stays open through proxies and idle timeouts
                    yield ": keepalive\n\n"  # pragma: no cover
        finally:
            # Clean up when client disconnects
            try:  # pragma: no cover
                _SUBSCRIBERS.remove(local_q)  # pragma: no cover
            except ValueError:  # pragma: no cover
                pass  # pragma: no cover

    resp = Response(event_stream(q), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'   # disable Nginx proxy buffering
    resp.headers['Connection'] = 'keep-alive'
    return resp


@orders_bp.route('/stream_web')  # pragma: no cover
@login_required
def stream_web():
    """Server-Sent Events stream for authenticated web users.

    Sends a ':keepalive' comment every 25 s so the connection is never idle
    long enough for a proxy or browser to drop it.
    """
    import queue as _queue
    import json as _json

    q = _queue.Queue()
    _SUBSCRIBERS.append(q)

    def event_stream(local_q):
        try:
            while True:
                try:
                    data = local_q.get(timeout=25)
                    yield f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    # Keepalive — prevents proxy / browser from closing idle connection
                    yield ": keepalive\n\n"
        finally:
            try:
                _SUBSCRIBERS.remove(local_q)
            except ValueError:
                pass

    resp = Response(event_stream(q), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    return resp


# Pipeline order for the status stepper — defined once here, passed to template
_MAIN_STATUSES = [
    OrderStatus.PENDING.value,
    OrderStatus.IN_PROGRESS.value,
    OrderStatus.PICKING.value,
    OrderStatus.INVOICING.value,
    OrderStatus.READY.value,
    OrderStatus.SHIPPED.value,
]
_EXTRA_STATUSES = [OrderStatus.CANCELLED.value, OrderStatus.ON_HOLD.value]


@orders_bp.route("/dashboard")
@login_required
def dashboard():  # pragma: no cover
    """Render the KPI dashboard"""
    return render_template("orders/dashboard.html")


@orders_bp.route("/api/dashboard-stats")
@login_required
def dashboard_stats():  # pragma: no cover
    """Calculate and return real-time KPIs"""
    target_date = request.args.get("date")
    if not target_date:
        target_date = datetime.datetime.now().strftime("%Y-%m-%d")

    order_mgr = current_app.order_status_mgr
    all_orders = order_mgr.get_all_orders()

    workload = {status.value: 0 for status in OrderStatus}
    created_today = 0
    shipped_today = 0
    warehouse_times = []
    
    for order in all_orders:
        status = order.get("status", "")
        if status in workload:
            workload[status] += 1
            
        doc_date = order.get("doc_date", "") or order.get("order_date", "")
        if doc_date.startswith(target_date):
            created_today += 1
            
        history = order.get("status_history", [])
        
        if status == OrderStatus.SHIPPED.value:
            for entry in history:
                if entry.get("status") == OrderStatus.SHIPPED.value and entry.get("timestamp", "").startswith(target_date):
                    shipped_today += 1
                    break
                    
        time_pendiente = None
        time_terminado = None
        for entry in history:
            if entry.get("status") == OrderStatus.PENDING.value and not time_pendiente:
                time_pendiente = entry.get("timestamp")
            if entry.get("status") == OrderStatus.PICKING.value and not time_terminado:
                time_terminado = entry.get("timestamp")
                
        if not time_pendiente and history:
            time_pendiente = history[0].get("timestamp")
            
        if time_pendiente and time_terminado:
            # Only average lead times of orders completed on the target date
            if time_terminado.startswith(target_date):
                try:
                    t1 = datetime.datetime.fromisoformat(time_pendiente)
                    t2 = datetime.datetime.fromisoformat(time_terminado)
                    diff = (t2 - t1).total_seconds() / 3600.0 # in hours
                    if diff > 0 and diff < 100: # filter anomalies
                        warehouse_times.append(diff)
                except Exception as e:
                    current_app.logger.warning(f"Ignored exception: {e}")

    avg_warehouse_time = sum(warehouse_times) / len(warehouse_times) if warehouse_times else 0

    return jsonify({
        "target_date": target_date,
        "workload": workload,
        "throughput": {
            "created_today": created_today,
            "shipped_today": shipped_today
        },
        "lead_times": {
            "warehouse_hours": round(avg_warehouse_time, 2)
        }
    })


@orders_bp.route("/api/audit-stats")
@login_required
def audit_stats():  # pragma: no cover
    """Calculate delays between SAP document creation and SAO reaction time"""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible", "audits": []}), 503

    limit = request.args.get("limit", 100, type=int)

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:
            from core.sap_connector import SAPHanaConnector
            sap = SAPHanaConnector()
            sap.connect()
            current_app.sap_connector = sap

        deliveries, invoices = sap.get_recent_deliveries_and_invoices_audit(limit=limit)
    except Exception as e:
        return jsonify({"error": f"Error al conectar con SAP: {e}", "audits": []}), 500

    order_mgr = current_app.order_status_mgr
    all_orders = order_mgr.get_all_orders()

    # Map doc_entry -> order
    entry_to_order = {}
    for o in all_orders:
        de = o.get("doc_entry")
        if de:
            entry_to_order[int(de)] = o

    audit_records = []
    delays = []

    # Process deliveries (SAP -> SAO Entregado)
    for d in deliveries:
        de = d["order_doc_entry"]
        if de in entry_to_order:
            order = entry_to_order[de]
            sao_time_str = None
            history = order.get("status_history", [])
            for entry in history:
                if entry.get("status") == OrderStatus.PICKING.value:
                    sao_time_str = entry.get("timestamp")
                    break

            if sao_time_str and d["sap_date"]:
                try:
                    t_sap = datetime.datetime.fromisoformat(d["sap_date"])
                    t_sao = datetime.datetime.fromisoformat(sao_time_str)
                    diff_min = (t_sao - t_sap).total_seconds() / 60.0

                    if diff_min >= 0 and diff_min < 10080:
                        delays.append(diff_min)
                        audit_records.append({
                            "order_id": order["order_id"],
                            "customer_name": order["customer_name"],
                            "doc_type": "Entrega",
                            "doc_num": d["doc_num"],
                            "sap_date": d["sap_date"],
                            "sao_date": sao_time_str,
                            "delay_min": round(diff_min, 1)
                        })
                except Exception as e:
                    current_app.logger.warning(f"Ignored exception: {e}")

    # Process invoices (SAP -> SAO Facturacion)
    for inv in invoices:
        de = inv["order_doc_entry"]
        if de in entry_to_order:
            order = entry_to_order[de]
            sao_time_str = None
            history = order.get("status_history", [])
            for entry in history:
                if entry.get("status") == OrderStatus.INVOICING.value:
                    sao_time_str = entry.get("timestamp")
                    break

            if sao_time_str and inv["sap_date"]:
                try:
                    t_sap = datetime.datetime.fromisoformat(inv["sap_date"])
                    t_sao = datetime.datetime.fromisoformat(sao_time_str)
                    diff_min = (t_sao - t_sap).total_seconds() / 60.0

                    if diff_min >= 0 and diff_min < 10080:
                        delays.append(diff_min)
                        audit_records.append({
                            "order_id": order["order_id"],
                            "customer_name": order["customer_name"],
                            "doc_type": "Factura",
                            "doc_num": inv["doc_num"],
                            "sap_date": inv["sap_date"],
                            "sao_date": sao_time_str,
                            "delay_min": round(diff_min, 1)
                        })
                except Exception as e:
                    current_app.logger.warning(f"Ignored exception: {e}")

    # Sort audit records by SAO detection timestamp DESC
    audit_records.sort(key=lambda x: x["sao_date"], reverse=True)

    avg_delay = sum(delays) / len(delays) if delays else 0.0
    max_delay = max(delays) if delays else 0.0
    under_10_count = sum(1 for d in delays if d <= 10.0)
    efficiency_pct = (under_10_count / len(delays) * 100.0) if delays else 100.0

    return jsonify({
        "audits": audit_records[:50],
        "metrics": {
            "avg_delay_min": round(avg_delay, 1),
            "max_delay_min": round(max_delay, 1),
            "efficiency_pct": round(efficiency_pct, 1),
            "total_audited": len(delays)
        }
    })


@orders_bp.route("/<order_id>")
@login_required
def detail(order_id):
    """Order detail view"""
    order_mgr = current_app.order_status_mgr
    order = order_mgr.get_order(order_id)

    if not order:
        return render_template("errors/404.html"), 404

    current_idx = (
        _MAIN_STATUSES.index(order["status"])
        if order.get("status") in _MAIN_STATUSES
        else -1
    )

    return render_template(
        "orders/detail.html",
        order=order,
        OrderStatus=OrderStatus,
        main_statuses=_MAIN_STATUSES,
        extra_statuses=_EXTRA_STATUSES,
        current_idx=current_idx,
    )


@orders_bp.route("/api/search")
@login_required
def global_search():  # pragma: no cover
    """Global fast search across local order cache"""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify({"results": []})
        
    order_mgr = current_app.order_status_mgr
    all_orders = order_mgr.get_all_orders()
    
    results = []
    for order in all_orders:
        if (query in str(order.get('order_id', '')).lower() or
            query in str(order.get('customer_name', '')).lower() or
            query in str(order.get('customer_code', '')).lower() or
            query in str(order.get('factura_number', '')).lower()):
            
            results.append({
                "id": order.get('order_id'),
                "title": f"Pedido #{order.get('order_id')}",
                "customer": order.get('customer_name', ''),
                "status": order.get('status', ''),
                "factura": order.get('factura_number', ''),
                "url": url_for('orders.detail', order_id=order.get('order_id'))
            })
            
            if len(results) >= 10:
                break
                
    return jsonify({"results": results})

@orders_bp.route("/<order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    """Update order status"""
    if not current_user.can_edit_orders():  # Operators can update status
        return jsonify({"error": "Sin permisos"}), 403

    data = request.get_json()
    new_status = data.get("status", "").strip() if data else ""
    notes = data.get("notes", "") if data else ""

    if not new_status:
        return jsonify({"error": "Estado requerido"}), 400

    # Common aliases / display-text → enum-value normalization
    STATUS_ALIASES = {
        "Facturado": "Facturacion",
        "Facturación": "Facturacion",
        "Preparando": "Entregado",
        "Preparado": "Entregado",
        "Terminado": "Entregado",
        "Entregado": "Entregado",
        "Listo para Envío": "Relacion de envio",
        "Listo para Envio": "Relacion de envio",
        "Entregado a almacen": "Relacion de envio",
        "Recibido por almacen": "Relacion de envio",
        "Relación de envío": "Relacion de envio",
        "Relacion de envio": "Relacion de envio",
        "Enviado": "Enviado al cliente",
        "Recibido por cliente": "Enviado al cliente",
        # Reverse mappings (old enum values → new enum values)
        "Terminado": "Entregado",
        "Relacion de envio": "Relacion de envio",
        "Enviado al cliente": "Enviado al cliente",
    }
    normalized = STATUS_ALIASES.get(new_status, new_status)

    # Validate status
    try:
        logging.info(
            f"update_status: order={order_id}, raw='{new_status}', normalized='{normalized}'"
        )
        status_enum = OrderStatus(normalized)
    except ValueError:
        # Fallback: try case-insensitive match against enum values
        status_enum = None
        for s in OrderStatus:
            if s.value.lower() == normalized.lower():
                status_enum = s
                break
        if status_enum is None:
            # Last resort: match by enum member name (e.g. "READY", "SHIPPED")
            try:
                status_enum = OrderStatus[normalized.upper().replace(" ", "_")]
            except KeyError:
                pass
        if status_enum is None:
            logging.warning(
                f"Invalid status '{new_status}' (normalized='{normalized}'), "
                f"valid: {[s.value for s in OrderStatus]}"
            )
            return jsonify({"error": f"Estado inválido: '{new_status}'"}), 400

    order_mgr = current_app.order_status_mgr

    # ── Business rule: block "Relacion de envio" without a factura ────
    if status_enum == OrderStatus.READY:  # "Relacion de envio"
        order = order_mgr.get_order(order_id)
        if order and not order.get("factura_number"):
            return jsonify({
                "error": "No se puede avanzar a 'Relación de envío' sin número de factura asignado en SAP."
            }), 422

    result = order_mgr.update_status(
        order_id, status_enum.value, current_user.username, notes
    )

    # Broadcast update to connected monitors
    if result:
        try:
            updated_order = order_mgr.get_order(order_id)
            _publish_event({
                "type": "order_updated",
                "order_id": str(order_id),
                "order": updated_order,
            })
            if order and order.get("status") != status_enum.value:  # pragma: no cover
                _publish_event({
                    "type": "status_changed",
                    "order_id": str(order_id),
                    "customer": order.get("customer_name", ""),
                    "from": order.get("status", ""),
                    "to": status_enum.value
                })
        except Exception:  # pragma: no cover
            pass  # pragma: no cover

    if result:
        return jsonify({"success": True, "order": result})

    return jsonify({"error": "Pedido no encontrado"}), 404


@orders_bp.route("/import-sap", methods=["POST"])
@login_required
def import_from_sap():
    """Import order from SAP"""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    data = request.get_json()
    order_number = data.get("order_number", "").strip()

    if not order_number:
        return jsonify({"error": "Número de pedido requerido"}), 400

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        order_data = sap.get_order_details(order_number)

        if not order_data:
            return (
                jsonify({"error": f"Pedido {order_number} no encontrado en SAP"}),
                404,
            )

        # Flatten SAP data structure for order_status_manager
        # SAP connector returns {'header': {...}, 'items': [...]}
        # but import_from_sap expects flat structure with DocNum at top level
        header = order_data.get("header", {})
        items = order_data.get("items", [])

        # Determine who updated it
        sap_user = header.get(
            "updater_name", header.get("creator_name", current_user.username)
        )

        flattened_order = {
            "DocNum": header.get("order_number"),
            "DocEntry": header.get("doc_entry"),
            "CardCode": header.get("customer_code"),
            "CardName": header.get("customer_name"),
            "DocDate": header.get("order_date"),
            "DocDueDate": header.get("delivery_date"),
            "DocTotal": header.get("total_value", 0),
            "DocCurrency": header.get("currency", "MXN"),
            "Comments": "",
            "items": items,
            "sap_status": header.get("sap_status", "Abierto"),
            "factura_number": header.get("factura_number"),
            "delivery_number": header.get("delivery_number"),
            "updated_by": sap_user,
            "created_by": header.get("creator_name"),
            "creator_name": header.get("creator_name"),
        }

        # Import to local status manager
        order_mgr = current_app.order_status_mgr
        result = order_mgr.import_from_sap(flattened_order, imported_by=sap_user)

        return jsonify({"success": True, "order": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@orders_bp.route("/<order_id>/label-printed", methods=["POST"])
@login_required
def label_printed(order_id):
    """Endpoint to be called when a shipping label is printed for an order.

    This will transition the local order status to `En Proceso` and notify
    connected monitor clients via SSE.
    """
    if not current_user.can_print_labels():
        return jsonify({"error": "Sin permisos"}), 403

    order_mgr = current_app.order_status_mgr

    # Move to In Progress
    success = order_mgr.update_status(
        order_id, OrderStatus.IN_PROGRESS.value, current_user.username, notes="Etiqueta impresa"
    )

    if not success:
        return jsonify({"error": "Pedido no encontrado"}), 404

    # Broadcast update
    try:
        updated_order = order_mgr.get_order(order_id)
        _publish_event({
            "type": "order_updated",
            "order_id": str(order_id),
            "order": updated_order,
        })
    except Exception:  # pragma: no cover
        pass  # pragma: no cover

    return jsonify({"success": True})


@orders_bp.route("/api/sga/label-printed", methods=["POST"])
@_require_sga_api_key
def sga_label_printed():
    """Webhook endpoint for SGA Production to notify Open-OMS when a label is
    printed.  SGA sends the exact order_id (DocNum) — no fuzzy item matching.

    Authenticated via X-API-Key header (shared SGA_API_KEY env var).
    CSRF-exempt: this is a machine-to-machine call, not a browser form.
    """
    data = request.get_json(silent=True) or {}

    order_id = str(data.get("order_id", "")).strip()
    station = str(data.get("station", "")).strip()

    if not order_id or not station:
        return jsonify({"error": "order_id and station are required"}), 400

    order_mgr = current_app.order_status_mgr
    order = order_mgr.get_order(order_id)

    if not order:
        # SGA printed a label, but order isn't loaded locally yet.
        # Try to dynamically import it from SAP if SAP is available.
        if current_app.sap_available:
            try:
                sap = current_app.sap_connector
                if not sap or not sap.connected:  # pragma: no cover
                    from core.sap_connector import SAPHanaConnector
                    sap = SAPHanaConnector()
                    sap.connect()
                    current_app.sap_connector = sap

                order_data = sap.get_order_details(order_id)
                if order_data:
                    header = order_data.get("header", {})
                    items = order_data.get("items", [])
                    sap_user = header.get("updater_name", header.get("creator_name", "SGA Webhook"))

                    flattened_order = {
                        "DocNum": header.get("order_number"),
                        "DocEntry": header.get("doc_entry"),
                        "CardCode": header.get("customer_code"),
                        "CardName": header.get("customer_name"),
                        "DocDate": header.get("order_date"),
                        "DocDueDate": header.get("delivery_date"),
                        "DocTotal": header.get("total_value", 0),
                        "DocCurrency": header.get("currency", "MXN"),
                        "Comments": "",
                        "items": items,
                        "sap_status": header.get("sap_status", "Abierto"),
                        "factura_number": header.get("factura_number"),
                        "delivery_number": header.get("delivery_number"),
                        "updated_by": sap_user,
                        "created_by": header.get("creator_name"),
                        "creator_name": header.get("creator_name"),
                    }
                    order = order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                    logging.info(f"SGA Webhook: Order {order_id} auto-imported from SAP.")
            except Exception as e:  # pragma: no cover
                logging.error(f"SGA Webhook: Failed to auto-import order {order_id} from SAP: {e}")

    if not order:
        # Still not found — enqueue for retry so we don't lose the event.
        # Return 202 Accepted so SGA doesn't log a failure.
        with _RETRY_LOCK:
            _WEBHOOK_RETRY_QUEUE.append({
                "order_id": order_id,
                "station":  station,
                "data":     data,
                "attempt":  0,
            })
        logging.warning(
            "SGA Webhook: Order %s not found — queued for retry "
            "(station=%s, queue_depth=%d)",
            order_id, station, len(_WEBHOOK_RETRY_QUEUE),
        )
        return jsonify({
            "accepted": True,
            "order_id": order_id,
            "message": "Order not loaded yet — will retry automatically",
        }), 202


    # Prevent status downgrade — don't move an order backwards
    current_status = order.get("status", "")
    target_status = OrderStatus.IN_PROGRESS.value
    if current_status in _MAIN_STATUSES:
        current_idx = _MAIN_STATUSES.index(current_status)
        target_idx = _MAIN_STATUSES.index(target_status)
        if current_idx > target_idx:
            return jsonify({
                "success": False,
                "order_id": order_id,
                "current_status": current_status,
                "message": f"Order already at '{current_status}', not downgrading",
            }), 409

    # Build audit notes
    items = data.get("items", [])
    event_type = data.get("event_type", "DIRECT_PRINT_JOB")
    notes = f"Impresión SGA (station={station}, type={event_type}"
    if items:
        notes += f", items={sorted(items)}"
    notes += ")"

    previous_status = current_status
    success = order_mgr.update_status(
        order_id, target_status, station, notes=notes
    )

    if not success:  # pragma: no cover
        return jsonify({"error": "Failed to update order"}), 500

    # Broadcast SSE update to connected monitors
    try:
        updated_order = order_mgr.get_order(order_id)
        _publish_event({
            "type": "order_updated",
            "order_id": str(order_id),
            "order": updated_order,
        })
        # Also fire status_changed so the monitor's notification bell rings
        _publish_event({
            "type": "status_changed",
            "order_id": str(order_id),
            "from": previous_status,
            "to": target_status,
            "customer": updated_order.get("customer_name", "") if updated_order else "",
        })
    except Exception:  # pragma: no cover
        pass  # pragma: no cover

    logging.info(
        f"SGA label-printed: order={order_id}, station={station}, "
        f"{previous_status} -> {target_status}"
    )

    return jsonify({
        "success": True,
        "order_id": order_id,
        "previous_status": previous_status,
        "new_status": target_status,
        "message": "Orden actualizada por impresión SGA",
    })


@orders_bp.route("/load-recent-sap", methods=["POST"])
@login_required
def load_recent_from_sap():
    """Load recent orders from SAP (bulk import)"""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    if not current_user.can_print_labels():
        return jsonify({"error": "Sin permisos"}), 403

    data = request.get_json() or {}
    limit = min(int(data.get("limit", 50)), 200)  # Max 200 orders at a time
    only_open = data.get("only_open", False)  # Default to False (All orders)

    logging.info(f"Load Recent SAP: limit={limit}, only_open={only_open}")

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        # Get recent orders from SAP
        recent_orders = sap.get_recent_orders(limit=limit, only_open=only_open)

        logging.info(f"Fetched {len(recent_orders)} orders from SAP")

        order_mgr = current_app.order_status_mgr
        imported_count = 0
        updated_count = 0

        for order_data in recent_orders:
            if not order_data or "header" not in order_data:  # pragma: no cover
                continue  # pragma: no cover

            header = order_data.get("header", {})
            items = order_data.get("items", [])

            # Determine user
            sap_user = header.get(
                "updater_name", header.get("creator_name", current_user.username)
            )

            # Flatten SAP data structure
            flattened_order = {
                "DocNum": header.get("order_number"),
                "DocEntry": header.get("doc_entry"),
                "CardCode": header.get("customer_code"),
                "CardName": header.get("customer_name"),
                "DocDate": header.get("order_date"),
                "DocDueDate": header.get("delivery_date"),
                "DocTotal": header.get("total_value", 0),
                "DocCurrency": header.get("currency", "MXN"),
                "Comments": "",
                "items": items,
                "sap_status": header.get("sap_status", "Abierto"),
                "factura_number": header.get("factura_number"),
                "delivery_number": header.get("delivery_number"),
                "updated_by": sap_user,
                "created_by": header.get("creator_name"),
                "creator_name": header.get("creator_name"),
            }

            order_id = str(flattened_order["DocNum"])

            # Check if already exists
            if order_id in order_mgr.orders:
                # Update delivery note number if not present
                if flattened_order.get("delivery_number") and not order_mgr.orders[order_id].get("delivery_number"):  # pragma: no cover
                    order_mgr.orders[order_id]["delivery_number"] = flattened_order["delivery_number"]
                    updated_count += 1

                # Update SAP status only
                if (
                    order_mgr.orders[order_id].get("sap_status")
                    != flattened_order["sap_status"]
                ):
                    order_mgr.orders[order_id]["sap_status"] = flattened_order[
                        "sap_status"
                    ]

                    # Only update last_updated / history when LOCAL status changes
                    new_local_status = order_mgr.orders[order_id].get("status")
                    local_changed = False
                    if flattened_order[
                        "sap_status"
                    ] == "Cerrado" and new_local_status not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ]:
                        new_local_status = OrderStatus.INVOICING.value
                        order_mgr.orders[order_id]["status"] = new_local_status
                        local_changed = True
                    elif (
                        flattened_order["sap_status"] == "Cancelado"
                        and new_local_status != OrderStatus.CANCELLED.value
                    ):
                        new_local_status = OrderStatus.CANCELLED.value
                        order_mgr.orders[order_id]["status"] = new_local_status
                        local_changed = True

                    if local_changed:
                        now_ts = datetime.datetime.now().isoformat()
                        order_mgr.orders[order_id]["last_updated"] = now_ts
                        order_mgr.orders[order_id]["updated_by"] = sap_user
                        order_mgr.orders[order_id]["status_history"].append(
                            {
                                "status": new_local_status,
                                "timestamp": now_ts,
                                "user": sap_user,
                                "notes": f"Auto-actualizado: {flattened_order['sap_status']}",
                            }
                        )
                    updated_count += 1
            else:
                # Import new order
                order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                imported_count += 1

        # Save all changes
        order_mgr._save_database()

        return jsonify(
            {
                "success": True,
                "imported": imported_count,
                "updated": updated_count,
                "total_fetched": len(recent_orders),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/sync-sap", methods=["POST"])
@login_required
def sync_sap_status():
    """Sync SAP status for all orders using a single batch query."""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    if not current_user.can_print_labels():
        return jsonify({"error": "Sin permisos"}), 403

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        order_mgr = current_app.order_status_mgr

        # Collect all order IDs as integers for batch query
        order_ids_int = []
        for oid in order_mgr.orders:
            try:
                order_ids_int.append(int(oid))
            except (ValueError, TypeError):  # pragma: no cover
                continue  # pragma: no cover

        if not order_ids_int:
            return jsonify({"success": True, "updated": 0, "total": 0})

        # Single batch query — fetches status for ALL orders at once
        logging.info(f"Batch-syncing {len(order_ids_int)} orders from SAP...")
        sap_statuses = sap.get_orders_status_batch(order_ids_int)
        logging.info(f"SAP returned status for {len(sap_statuses)} orders")

        updated_count = 0
        now_iso = datetime.datetime.now().isoformat()

        for order_id, order in list(order_mgr.orders.items()):
            try:
                doc_num = int(order_id)
            except (ValueError, TypeError):  # pragma: no cover
                continue  # pragma: no cover

            sap_data = sap_statuses.get(doc_num)
            if not sap_data:
                continue

            new_sap_status = sap_data["sap_status"]
            sap_user = sap_data.get("updater_name", "SAP System")

            # Update only if SAP status changed
            if order.get("sap_status") != new_sap_status:
                order["sap_status"] = new_sap_status
                # updated_by tracks who last touched SAP data, but last_updated
                # is reserved for actual LOCAL status changes (see update_status())
                order["updated_by"] = sap_user

                # If SAP shows "Cerrado" and local is not delivered, update local status.
                # update_status() will set last_updated correctly.
                if new_sap_status == "Cerrado" and order.get("status") not in [
                    OrderStatus.INVOICING.value,
                    OrderStatus.READY.value,
                    OrderStatus.SHIPPED.value,
                ]:
                    order_mgr.update_status(
                        order_id,
                        OrderStatus.READY.value,
                        sap_user,
                        "Auto-actualizado: Cerrado en SAP",
                    )

                updated_count += 1

        # Save changes
        order_mgr._save_database()

        return jsonify(
            {"success": True, "updated": updated_count, "total": len(order_mgr.orders)}
        )

    except Exception as e:
        logging.error(f"SAP sync error: {e}")
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/add", methods=["POST"])
@login_required
def add_manual():
    """Add manual order"""
    if not current_user.can_print_labels():
        return jsonify({"error": "Sin permisos"}), 403

    data = request.get_json()

    required = ["order_id", "customer_name"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    order_mgr = current_app.order_status_mgr

    # Check if exists
    if order_mgr.get_order(data["order_id"]):
        return jsonify({"error": "Pedido ya existe"}), 400

    # Create order
    order_data = {
        "DocNum": data["order_id"],
        "CardCode": data.get("customer_code", ""),
        "CardName": data["customer_name"],
        "DocDate": data.get("doc_date", ""),
        "items": data.get("items", []),
    }

    result = order_mgr.import_from_sap(order_data, imported_by=current_user.username)

    return jsonify({"success": True, "order": result})


@orders_bp.route("/<order_id>/delete", methods=["DELETE"])
@login_required
def delete_order(order_id):
    """Delete order - Admin only"""
    if not current_user.can_edit_orders():
        return jsonify({"error": "Solo administradores pueden eliminar pedidos"}), 403

    order_mgr = current_app.order_status_mgr

    if order_mgr.delete_order(order_id):
        return jsonify({"success": True})

    return jsonify({"error": "Pedido no encontrado"}), 404


@orders_bp.route("/visor/sync", methods=["POST"])
@login_required
def visor_sync():
    """Lightweight sync for visor auto-refresh"""
    # Any authenticated user can trigger this (viewers included)
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        # Get recent active orders (limit 50, only open)
        # This is faster than a full sync
        recent_orders = sap.get_recent_orders(limit=50, only_open=True)

        order_mgr = current_app.order_status_mgr
        updated_count = 0
        new_count = 0

        for order_data in recent_orders:
            if not order_data or "header" not in order_data:  # pragma: no cover
                continue  # pragma: no cover

            header = order_data.get("header", {})
            items = order_data.get("items", [])

            # Determine user
            sap_user = header.get(
                "updater_name", header.get("creator_name", "auto_sync")
            )

            # Simplified import structure
            flattened_order = {
                "DocNum": header.get("order_number"),
                "DocEntry": header.get("doc_entry"),
                "CardCode": header.get("customer_code"),
                "CardName": header.get("customer_name"),
                "DocDate": header.get("order_date"),
                "DocDueDate": header.get("delivery_date"),
                "DocTotal": header.get("total_value", 0),
                "DocCurrency": header.get("currency", "MXN"),
                "sap_status": header.get("sap_status", "Abierto"),
                "factura_number": header.get("factura_number"),
                "delivery_number": header.get("delivery_number"),
                "items": items,
                "updated_by": sap_user,
                "created_by": header.get("creator_name"),
                "creator_name": header.get("creator_name"),
            }

            order_id = str(flattened_order["DocNum"])

            # Check if exists
            if order_id in order_mgr.orders:
                needs_update = False

                # Update SAP status if changed
                current_sap_status = order_mgr.orders[order_id].get("sap_status")
                new_sap_status = flattened_order["sap_status"]

                # Always sync factura_number from SAP first (before status logic)
                new_fact = flattened_order.get("factura_number")
                cur_fact = order_mgr.orders[order_id].get("factura_number")
                if new_fact and cur_fact != new_fact:
                    order_mgr.orders[order_id]["factura_number"] = new_fact
                    cur_fact = new_fact
                    needs_update = True

                if current_sap_status != new_sap_status:
                    order_mgr.orders[order_id]["sap_status"] = new_sap_status
                    # Only stamp last_updated when LOCAL status is also changed
                    current_local = order_mgr.orders[order_id].get("status")
                    effective_fact = order_mgr.orders[order_id].get("factura_number")
                    if new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ] and effective_fact:  # pragma: no cover
                        order_mgr.orders[order_id]["status"] = OrderStatus.READY.value
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
                    elif new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ] and not effective_fact:
                        order_mgr.orders[order_id]["status"] = OrderStatus.INVOICING.value
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
                    elif (
                        new_sap_status == "Cancelado"
                        and current_local != OrderStatus.CANCELLED.value
                    ):
                        order_mgr.orders[order_id]["status"] = OrderStatus.CANCELLED.value
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
                    needs_update = True

                if needs_update:
                    updated_count += 1
            else:
                # New order found
                order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                new_count += 1

        if updated_count > 0 or new_count > 0:
            order_mgr._save_database()

        # Auto-status: Delivery Notes → Terminado, Invoices → Facturacion
        try:
            auto_count = _check_delivery_and_invoice(sap, order_mgr, recent_orders)
            if auto_count > 0:  # pragma: no cover
                updated_count += auto_count
        except Exception as e:  # pragma: no cover
            logging.warning(f"Visor auto-status error: {e}")

        return jsonify({"success": True, "updated": updated_count, "new": new_count})

    except Exception as e:
        import logging
        logging.warning(f"Visor sync error: {e}")
        return jsonify({"success": False, "error": str(e), "updated": 0, "new": 0}), 200


@orders_bp.route("/visor")
@login_required
def visor():
    """Sales team visor dashboard"""
    order_mgr = current_app.order_status_mgr

    # Get active orders (exclude delivered/cancelled)
    active_orders = order_mgr.get_active_orders()

    # Calculate stats
    stats = {
        "total_active": len(active_orders),
        "pending": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PENDING.value]
        ),
        "picking": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PICKING.value]
        ),
        "ready": len(
            [o for o in active_orders if o.get("status") == OrderStatus.READY.value]
        ),
        "shipped": len(
            [o for o in active_orders if o.get("status") == OrderStatus.SHIPPED.value]
        ),
    }

    return render_template(
        "orders/visor.html",
        orders=active_orders,
        stats=stats,
        OrderStatus=OrderStatus,
        now=datetime.datetime.now(),
    )


@orders_bp.route("/api/active")
@login_required
def api_active_orders():
    """API to get active orders for visor (JSON)"""
    order_mgr = current_app.order_status_mgr

    # Get active orders
    active_orders = order_mgr.get_active_orders()

    # Calculate stats
    stats = {
        "total_active": len(active_orders),
        "pending": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PENDING.value]
        ),
        "picking": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PICKING.value]
        ),
        "ready": len(
            [o for o in active_orders if o.get("status") == OrderStatus.READY.value]
        ),
        "shipped": len(
            [o for o in active_orders if o.get("status") == OrderStatus.SHIPPED.value]
        ),
    }

    return jsonify(
        {
            "orders": active_orders,
            "stats": stats,
            "generated_at": datetime.datetime.now().isoformat(),
        }
    )


@orders_bp.route("/monitor")
@login_required
def monitor():
    """Seller tracking panel — login required for role-based filtering.
    Sellers see only their own orders; managers/admins see all."""
    return render_template("orders/monitor.html", now=datetime.datetime.now())


@orders_bp.route("/api/seller/orders")
@login_required
def api_seller_orders():
    """API for the Monitor panel — returns orders filtered by seller identity.
    - seller role: only orders where created_by matches user's sap_seller_name
    - sell_manager / admin / operator: all orders (with optional ?seller= filter)
    """
    order_mgr = current_app.order_status_mgr
    active_orders = order_mgr.get_active_orders()

    # Role-based filtering
    user = current_user
    can_see_all = user.can_see_all_orders()
    seller_filter = request.args.get("seller", "").strip()

    if not can_see_all:
        # Seller role — filter to own SAP seller name
        sap_name = getattr(user, "sap_seller_name", "") or ""
        if sap_name:
            active_orders = [
                o
                for o in active_orders
                if (o.get("created_by", "") or "").upper() == sap_name.upper()
            ]
        else:
            # No SAP name configured — return empty
            active_orders = []
    elif seller_filter:
        # Manager/admin filtering by specific seller
        active_orders = [
            o
            for o in active_orders
            if (o.get("created_by", "") or "").upper() == seller_filter.upper()
        ]

    # Build unique seller list (for the filter dropdown)
    all_orders = order_mgr.get_active_orders()
    sellers = sorted(
        set(o.get("created_by", "") for o in all_orders if o.get("created_by"))
    )

    # Stats
    stats = {
        "total_active": len(active_orders),
        "pending": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PENDING.value]
        ),
        "in_progress": len(
            [
                o
                for o in active_orders
                if o.get("status") == OrderStatus.IN_PROGRESS.value
            ]
        ),
        "picking": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PICKING.value]
        ),
        "invoicing": len(
            [o for o in active_orders if o.get("status") == OrderStatus.INVOICING.value]
        ),
        "ready": len(
            [o for o in active_orders if o.get("status") == OrderStatus.READY.value]
        ),
        "shipped": len(
            [o for o in active_orders if o.get("status") == OrderStatus.SHIPPED.value]
        ),
    }

    return jsonify(
        {
            "orders": active_orders,
            "stats": stats,
            "sellers": sellers,
            "can_see_all": can_see_all,
            "current_seller": getattr(user, "sap_seller_name", ""),
            "generated_at": datetime.datetime.now().isoformat(),
        }
    )


@orders_bp.route("/api/public/active")
@_require_monitor_token
def public_api_active_orders():
    """Public API for monitor dashboard (token-protected when MONITOR_TOKEN is set).
    Returns only non-sensitive order fields (no totals, no customer codes)."""
    order_mgr = current_app.order_status_mgr

    # Get params
    try:
        limit = int(request.args.get("limit", 50))
        limit = max(1, min(limit, 200))  # Clamp between 1 and 200
    except ValueError:
        limit = 50

    # Get active orders
    active_orders = order_mgr.get_active_orders()

    # Apply limit (most recent first based on logic in get_active_orders or here)
    # get_active_orders usually returns all, so we slice here if needed
    # But usually we want *all* active ones. If limit is for "recently updated",
    # we might need to sort. Let's assume frontend wants top N.
    # We'll just return all for now if they fit, or slice.
    if len(active_orders) > limit:
        active_orders = active_orders[:limit]

    # Calculate stats
    stats = {
        "total_active": len(active_orders),
        "pending": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PENDING.value]
        ),
        "in_progress": len(
            [
                o
                for o in active_orders
                if o.get("status") == OrderStatus.IN_PROGRESS.value
            ]
        ),
        "picking": len(
            [o for o in active_orders if o.get("status") == OrderStatus.PICKING.value]
        ),
        "ready": len(
            [o for o in active_orders if o.get("status") == OrderStatus.READY.value]
        ),
        "shipped": len(
            [o for o in active_orders if o.get("status") == OrderStatus.SHIPPED.value]
        ),
    }

    return jsonify(
        {
            "orders": active_orders,
            "stats": stats,
            "generated_at": datetime.datetime.now().isoformat(),
        }
    )


@orders_bp.route("/api/public/sync", methods=["POST"])
@_require_monitor_token
def public_api_sync():
    """Public API to trigger SAP sync (token-protected when MONITOR_TOKEN is set)"""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        # Get recent active orders (limit 50, only open)
        recent_orders = sap.get_recent_orders(limit=50, only_open=True)

        order_mgr = current_app.order_status_mgr
        updated_count = 0
        new_count = 0

        for order_data in recent_orders:
            if not order_data or "header" not in order_data:  # pragma: no cover
                continue  # pragma: no cover

            header = order_data.get("header", {})
            items = order_data.get("items", [])

            # Determine user
            sap_user = header.get(
                "updater_name", header.get("creator_name", "auto_sync")
            )

            # Simplified import structure
            flattened_order = {
                "DocNum": header.get("order_number"),
                "DocEntry": header.get("doc_entry"),
                "CardCode": header.get("customer_code"),
                "CardName": header.get("customer_name"),
                "DocDate": header.get("order_date"),
                "DocDueDate": header.get("delivery_date"),
                "DocTotal": header.get("total_value", 0),
                "DocCurrency": header.get("currency", "MXN"),
                "sap_status": header.get("sap_status", "Abierto"),
                "factura_number": header.get("factura_number"),
                "delivery_number": header.get("delivery_number"),
                "items": items,
                "updated_by": sap_user,
                "created_by": header.get("creator_name"),
                "creator_name": header.get("creator_name"),
            }

            order_id = str(flattened_order["DocNum"])

            # Check if exists
            if order_id in order_mgr.orders:
                needs_update = False
                # Update SAP status if changed
                current_sap_status = order_mgr.orders[order_id].get("sap_status")
                new_sap_status = flattened_order["sap_status"]

                # Always sync factura_number from SAP first (before status logic)
                new_fact = flattened_order.get("factura_number")
                cur_fact = order_mgr.orders[order_id].get("factura_number")
                if new_fact and cur_fact != new_fact:
                    order_mgr.orders[order_id]["factura_number"] = new_fact
                    cur_fact = new_fact
                    needs_update = True

                if current_sap_status != new_sap_status:
                    order_mgr.orders[order_id]["sap_status"] = new_sap_status
                    # Only stamp last_updated when LOCAL status is also changed
                    current_local = order_mgr.orders[order_id].get("status")
                    effective_fact = order_mgr.orders[order_id].get("factura_number")
                    if new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ] and effective_fact:
                        order_mgr.orders[order_id]["status"] = OrderStatus.READY.value  # pragma: no cover
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()  # pragma: no cover
                    elif new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ] and not effective_fact:
                        order_mgr.orders[order_id]["status"] = OrderStatus.INVOICING.value
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
                    elif (
                        new_sap_status == "Cancelado"
                        and current_local != OrderStatus.CANCELLED.value
                    ):
                        order_mgr.orders[order_id]["status"] = OrderStatus.CANCELLED.value
                        order_mgr.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
                    needs_update = True

                if needs_update:
                    updated_count += 1
            else:
                # New order found
                order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                new_count += 1

        if updated_count > 0 or new_count > 0:
            order_mgr._save_database()

        # Auto-status: Delivery Notes → Terminado, Invoices → Facturacion
        try:
            auto_count = _check_delivery_and_invoice(sap, order_mgr, recent_orders)
            if auto_count > 0:
                updated_count += auto_count  # pragma: no cover
        except Exception as e:  # pragma: no cover
            logging.warning(f"Public sync auto-status error: {e}")  # pragma: no cover

        return jsonify({"success": True, "updated": updated_count, "new": new_count})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Module-level sync cache ─────────────────────────────────────────
_last_sap_sync = 0  # epoch timestamp of last SAP sync
_SAP_SYNC_INTERVAL = 120  # seconds between SAP syncs (real time)
_sap_sync_lock = threading.Lock()  # prevents overlapping SAP syncs


@orders_bp.route("/api/refresh")
@login_required
def api_refresh_orders():
    """
    Combined endpoint: optionally sync with SAP, reconcile mismatches,
    then return the full order list.  The auto-refresh timer calls this.
    SAP sync is throttled to once every 2 minutes to avoid overloading.
    """
    import time as _time

    global _last_sap_sync

    order_mgr = current_app.order_status_mgr
    sap_synced = False
    sap_updated = 0
    sap_new = 0

    # ── Throttled SAP sync (non-blocking lock) ────────────────────────
    now = _time.time()
    if current_app.sap_available and (now - _last_sap_sync) >= _SAP_SYNC_INTERVAL:
        # Non-blocking: skip sync if another thread is already syncing
        acquired = _sap_sync_lock.acquire(blocking=False)
        if acquired:
            try:
                # Re-check after acquiring lock (another thread may have just finished)
                now = _time.time()
                if (now - _last_sap_sync) >= _SAP_SYNC_INTERVAL:
                    try:
                        sap = current_app.sap_connector
                        if not sap or not sap.connected:  # pragma: no cover
                            from core.sap_connector import SAPHanaConnector  # pragma: no cover

                            sap = SAPHanaConnector()  # pragma: no cover
                            sap.connect()  # pragma: no cover
                            current_app.sap_connector = sap  # pragma: no cover

                        recent_orders = sap.get_recent_orders(limit=50, only_open=False)

                        for order_data in recent_orders:
                            if not order_data or "header" not in order_data:  # pragma: no cover
                                continue  # pragma: no cover
                            header = order_data.get("header", {})
                            items = order_data.get("items", [])
                            sap_user = header.get(
                                "updater_name", header.get("creator_name", "auto_sync")
                            )

                            flattened = {
                                "DocNum": header.get("order_number"),
                                "CardCode": header.get("customer_code"),
                                "CardName": header.get("customer_name"),
                                "DocDate": header.get("order_date"),
                                "DocDueDate": header.get("delivery_date"),
                                "DocTotal": header.get("total_value", 0),
                                "DocCurrency": header.get("currency", "MXN"),
                                "sap_status": header.get("sap_status", "Abierto"),
                                "factura_number": header.get("factura_number"),
                                "items": items,
                                "updated_by": sap_user,
                            }

                            oid = str(flattened["DocNum"])
                            if oid in order_mgr.orders:
                                cur_sap = order_mgr.orders[oid].get("sap_status")
                                new_sap = flattened["sap_status"]
                                cur_fact = order_mgr.orders[oid].get("factura_number")
                                new_fact = flattened.get("factura_number")

                                needs_update = False

                                if cur_sap != new_sap:
                                    # Update SAP status silently — last_updated is handled by
                                    # reconcile_statuses() below when local status needs to change.
                                    order_mgr.orders[oid]["sap_status"] = new_sap
                                    needs_update = True

                                if new_fact and cur_fact != new_fact:
                                    order_mgr.orders[oid]["factura_number"] = new_fact
                                    needs_update = True

                                if needs_update:
                                    sap_updated += 1
                            else:
                                order_mgr.import_from_sap(flattened, imported_by=sap_user)
                                sap_new += 1

                        if sap_updated > 0 or sap_new > 0:
                            order_mgr._save_database()

                        # ── Auto-status: Delivery Notes → Terminado ───────
                        # ── Auto-status: Invoices → Facturacion ───────────
                        try:
                            _auto_status_count = _check_delivery_and_invoice(
                                sap, order_mgr, recent_orders
                            )
                            if _auto_status_count > 0:
                                sap_updated += _auto_status_count  # pragma: no cover
                        except Exception as e:  # pragma: no cover
                            logging.warning(f"Auto-status check error: {e}")  # pragma: no cover

                        _last_sap_sync = now
                        sap_synced = True
                    except Exception as e:
                        logging.warning(f"Background SAP sync error: {e}")
            finally:
                _sap_sync_lock.release()

    # ── Reconcile mismatched statuses ─────────────────────────────────
    reconciled = order_mgr.reconcile_statuses()

    # ── Build response (same logic as api_list_orders) ────────────────
    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    orders = list(order_mgr.orders.values())

    if status_filter:
        orders = [o for o in orders if o.get("status") == status_filter]
    if search:
        sl = search.lower()
        orders = [
            o
            for o in orders
            if (
                sl in str(o.get("order_id", "")).lower()
                or sl in str(o.get("customer_name", "")).lower()
                or sl in str(o.get("customer_code", "")).lower()
            )
        ]

    orders.sort(
        key=lambda x: (
            int(x.get("order_id", 0)) if str(x.get("order_id", "")).isdigit() else 0
        ),
        reverse=True,
    )

    status_counts = {}
    for status in OrderStatus:
        status_counts[status.value] = len(
            [o for o in order_mgr.orders.values() if o.get("status") == status.value]
        )

    return jsonify(
        {
            "orders": orders,
            "status_counts": status_counts,
            "sap_synced": sap_synced,
            "sap_updated": sap_updated,
            "sap_new": sap_new,
            "reconciled": reconciled,
            "generated_at": datetime.datetime.now().isoformat(),
        }
    )


@orders_bp.route("/api/list")
@login_required
def api_list_orders():
    """API to get all orders for index (JSON) - supports search/filter"""
    order_mgr = current_app.order_status_mgr

    # Get params
    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    # Get all orders
    orders = list(order_mgr.orders.values())

    # Filter by status
    if status_filter:
        orders = [o for o in orders if o.get("status") == status_filter]

    # Filter by search
    if search:
        search_lower = search.lower()
        orders = [
            o
            for o in orders
            if (
                search_lower in str(o.get("order_id", "")).lower()
                or search_lower in str(o.get("customer_name", "")).lower()
                or search_lower in str(o.get("customer_code", "")).lower()
            )
        ]

    # Sort
    orders.sort(
        key=lambda x: (
            int(x.get("order_id", 0)) if str(x.get("order_id", "")).isdigit() else 0
        ),
        reverse=True,
    )

    # Status counts for filter badges
    status_counts = {}
    for status in OrderStatus:
        count = len(
            [o for o in order_mgr.orders.values() if o.get("status") == status.value]
        )
        status_counts[status.value] = count

    return jsonify(
        {
            "orders": orders,
            "status_counts": status_counts,
            "generated_at": datetime.datetime.now().isoformat(),
        }
    )


# ─── Weather proxy (cached) ──────────────────────────────────────────
@orders_bp.route("/api/public/weather")
def public_api_weather():
    """Proxy OpenWeatherMap with 30-min cache (no login required)"""
    global _weather_cache

    CACHE_DURATION = 1800  # 30 minutes
    API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
    if not API_KEY:
        return jsonify(
            {
                "temp": None,
                "condition": "Clear",
                "condition_id": 800,
                "description": "API key not configured",
                "city": "N/A",
                "clouds": 0,
            }
        )
    default_city = os.environ.get("WEATHER_CITY", "Guadalajara,MX")
    city = request.args.get("city", default_city)

    now = time.time()
    cache_key = city.lower().strip()

    # Return cached if fresh
    if (
        _weather_cache.get("data")
        and _weather_cache.get("city") == cache_key
        and (now - _weather_cache.get("timestamp", 0)) < CACHE_DURATION
    ):
        return jsonify(_weather_cache["data"])

    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={urllib.request.quote(city)}"
            f"&appid={API_KEY}&units=metric&lang=es"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SGA-Monitor/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json_mod.loads(resp.read().decode())

        result = {
            "temp": round(raw["main"]["temp"]),
            "feels_like": round(raw["main"]["feels_like"]),
            "humidity": raw["main"]["humidity"],
            "condition": raw["weather"][0]["main"],
            "condition_id": raw["weather"][0]["id"],
            "description": raw["weather"][0]["description"],
            "icon": raw["weather"][0]["icon"],
            "wind_speed": round(raw.get("wind", {}).get("speed", 0), 1),
            "clouds": raw.get("clouds", {}).get("all", 0),
            "city": raw.get("name", city.split(",")[0]),
            "sunrise": raw["sys"].get("sunrise"),
            "sunset": raw["sys"].get("sunset"),
        }

        _weather_cache = {"data": result, "timestamp": now, "city": cache_key}
        return jsonify(result)

    except Exception as e:
        current_app.logger.warning(f"Weather API error: {e}")
        if _weather_cache.get("data"):  # pragma: no cover
            return jsonify(_weather_cache["data"])  # pragma: no cover
        return jsonify(
            {
                "temp": None,
                "condition": "Clear",
                "condition_id": 800,
                "description": "sin datos",
                "city": city.split(",")[0],
                "clouds": 0,
            }
        )


# ─── Facturas del Día ────────────────────────────────────────────────────────


@orders_bp.route("/facturas")
@login_required
def facturas():
    """Facturas del Día — daily invoices dashboard."""
    return render_template(
        "orders/facturas.html",
        sap_available=current_app.sap_available,
        now=datetime.datetime.now(),
    )


@orders_bp.route("/api/facturas")
@login_required
def api_facturas():
    """JSON API returning today's invoices from SAP."""
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible", "invoices": [], "stats": {}}), 503

    date_filter = request.args.get("date", "").strip() or None
    extra_invoices_str = request.args.get("extra_invoices", "").strip()

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        overrides = getattr(current_app, "factura_metadata_mgr", None)
        db_date = date_filter or datetime.date.today().isoformat()
        db_extras = overrides.get_daily_extras(db_date) if overrides else []

        # Merge query params and database extras
        req_extras = [int(x) for x in extra_invoices_str.split(",") if x.strip().isdigit()] if extra_invoices_str else []
        combined_extras = list(set(db_extras + req_extras))
        extra_invoice_numbers = combined_extras if combined_extras else None

        invoices = sap.get_todays_invoices(date_str=date_filter, extra_invoice_numbers=extra_invoice_numbers)

        # Cross-reference with order_status_mgr to determine Recibido/Entrega flags
        order_mgr = current_app.order_status_mgr
        factura_to_order = {
            str(order.get('factura_number')): order 
            for order in order_mgr.orders.values() 
            if order.get('factura_number')
        }

        # Fetch category overrides
        category_overrides, color_overrides, custom_names = overrides.get_overrides() if overrides else ({}, {}, {})

        for inv in invoices:
            inv_num_str = str(inv['invoice_number'])
            order = factura_to_order.get(inv_num_str)
            if order:  # pragma: no cover
                status = order.get('status')
                inv['recibido'] = status in [OrderStatus.READY.value, OrderStatus.SHIPPED.value]
                inv['entrega'] = status == OrderStatus.SHIPPED.value
                inv['related_order_id'] = order.get('order_id')
                inv['observaciones'] = order.get('observaciones', '')
                inv['order_status'] = status
                inv['order_sap_status'] = order.get('sap_status')
            else:
                inv['recibido'] = False
                inv['entrega'] = False
                inv['related_order_id'] = None
                inv['observaciones'] = ''
                inv['order_status'] = None
                inv['order_sap_status'] = None

            # Override category if set
            inv_num_int = int(inv['invoice_number'])
            if inv_num_int in category_overrides:  # pragma: no cover
                override_val = category_overrides[inv_num_int]
                if override_val.strip().upper() in ["ENVIO LOCAL", "ENVÍO LOCAL"]:
                    override_val = "LOCAL"
                inv['shipping_type'] = override_val

        # Calculate stats
        total_mxn = sum(i["total"] for i in invoices if i["currency"] == "MXN")
        total_usd = sum(i["total"] for i in invoices if i["currency"] == "USD")
        active = [i for i in invoices if i.get("status") == "Abierta"]
        cancelled = [i for i in invoices if i["status"] == "Cancelada"]
        closed = [i for i in invoices if i["status"] == "Cerrada"]

        stats = {
            "total_count": len(invoices),
            "active_count": len(active),
            "cancelled_count": len(cancelled),
            "closed_count": len(closed),
            "total_mxn": round(total_mxn, 2),
            "total_usd": round(total_usd, 2),
        }

        # Convert keys to strings for JSON compatibility
        row_colors = {str(k): v for k, v in color_overrides.items()}
        custom_customer_names = {str(k): v for k, v in custom_names.items()}
        manual_order = overrides.get_daily_order(db_date) if overrides else []
        manual_order = [str(x) for x in manual_order]

        return jsonify({
            "invoices": invoices,
            "stats": stats,
            "generated_at": datetime.datetime.now().isoformat(),
            "manual_order": manual_order,
            "extra_invoices": db_extras,
            "custom_customer_names": custom_customer_names,
            "row_colors": row_colors,
        })

    except Exception as e:
        logging.error(f"Facturas API error: {e}")
        return jsonify({"error": str(e), "invoices": [], "stats": {}}), 500


@orders_bp.route("/api/facturas/<int:invoice_number>/category", methods=["POST"])
@login_required
def api_update_factura_category(invoice_number):  # pragma: no cover
    """Save user-selected category override for an invoice and broadcast changes."""
    try:
        data = request.get_json()
        if not data or "category" not in data:
            return jsonify({"success": False, "error": "Missing category"}), 400
        
        mgr = getattr(current_app, "factura_metadata_mgr", None)
        if not mgr:
            return jsonify({"success": False, "error": "Metadata manager not available"}), 500
            
        success = mgr.save_override(invoice_number, data["category"])
        if success:
            _publish_event({
                "type": "factura_category_changed",
                "invoice_number": invoice_number,
                "category": data["category"]
            })
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Error updating category: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/api/facturas/<int:invoice_number>/color", methods=["POST"])
@login_required
def api_update_factura_color(invoice_number):  # pragma: no cover
    """Save user-selected color for an invoice row and broadcast changes."""
    try:
        data = request.get_json()
        if not data or "color" not in data:
            return jsonify({"success": False, "error": "Missing color"}), 400
        
        mgr = getattr(current_app, "factura_metadata_mgr", None)
        if not mgr:
            return jsonify({"success": False, "error": "Metadata manager not available"}), 500
            
        success = mgr.save_color(invoice_number, data["color"])
        if success:
            _publish_event({
                "type": "factura_color_changed",
                "invoice_number": invoice_number,
                "color": data["color"]
            })
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Error updating color: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/api/facturas/<int:invoice_number>/customer-name", methods=["POST"])
@login_required
def api_update_factura_customer_name(invoice_number):  # pragma: no cover
    """Save custom customer name for an invoice (e.g. Ventas Mostrador) and broadcast changes."""
    try:
        data = request.get_json()
        if not data or "customer_name" not in data:
            return jsonify({"success": False, "error": "Missing customer_name"}), 400
        
        mgr = getattr(current_app, "factura_metadata_mgr", None)
        if not mgr:
            return jsonify({"success": False, "error": "Metadata manager not available"}), 500
            
        success = mgr.save_custom_customer_name(invoice_number, data["customer_name"])
        if success:
            _publish_event({
                "type": "factura_customer_name_changed",
                "invoice_number": invoice_number,
                "customer_name": data["customer_name"]
            })
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Error updating customer name: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/api/facturas/manual-order", methods=["POST"])
@login_required
def api_update_factura_manual_order():  # pragma: no cover
    """Save manual sorting order of invoices for a specific date and broadcast changes."""
    try:
        data = request.get_json()
        if not data or "date" not in data or "manual_order" not in data:
            return jsonify({"success": False, "error": "Missing date or manual_order"}), 400
        
        mgr = getattr(current_app, "factura_metadata_mgr", None)
        if not mgr:
            return jsonify({"success": False, "error": "Metadata manager not available"}), 500
            
        success = mgr.save_daily_order(data["date"], data["manual_order"])
        if success:
            _publish_event({
                "type": "factura_manual_order_changed",
                "date": data["date"],
                "manual_order": data["manual_order"]
            })
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Error updating manual order: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/api/facturas/extra", methods=["POST"])
@login_required
def api_update_factura_extras():  # pragma: no cover
    """Save manually added extra invoices for a specific date and broadcast changes."""
    try:
        data = request.get_json()
        if not data or "date" not in data or "extra_invoices" not in data:
            return jsonify({"success": False, "error": "Missing date or extra_invoices"}), 400
        
        mgr = getattr(current_app, "factura_metadata_mgr", None)
        if not mgr:
            return jsonify({"success": False, "error": "Metadata manager not available"}), 500
            
        success = mgr.save_daily_extras(data["date"], data["extra_invoices"])
        if success:
            _publish_event({
                "type": "factura_extras_changed",
                "date": data["date"],
                "extra_invoices": data["extra_invoices"]
            })
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Error updating extra invoices: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/api/facturas/export")
@login_required
def api_facturas_export():  # pragma: no cover
    if not current_app.sap_available:
        return jsonify({"error": "SAP no disponible"}), 503

    date_filter = request.args.get("date", "").strip() or None
    status_filter = request.args.get("status", "").strip() or None

    # Validate date format to prevent SAP query errors
    if date_filter:
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_filter):
            return jsonify({"error": f"Formato de fecha inválido: {date_filter}. Use YYYY-MM-DD."}), 400
        try:
            datetime.datetime.strptime(date_filter, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": f"Fecha inválida: {date_filter}"}), 400

    try:
        sap = current_app.sap_connector
        invoices = sap.get_todays_invoices(date_str=date_filter)

        # Apply the same status filter the web view uses
        if status_filter:
            invoices = [i for i in invoices if i['status'] == status_filter]

        # Excluir facturas canceladas
        invoices = [i for i in invoices if i.get('status') != 'Cancelada']

        order_mgr = current_app.order_status_mgr
        factura_to_order = {
            str(order.get('factura_number')): order 
            for order in order_mgr.orders.values() 
            if order.get('factura_number')
        }

        # Fetch category overrides
        overrides = getattr(current_app, "factura_metadata_mgr", None)
        category_overrides = overrides.get_overrides() if overrides else {}

        locals_inv = []
        paqueteria_inv = []
        gdl_inv = []
        mty_inv = []
        ira_inv = []
        flete_inv = []

        for inv in invoices:
            # Override category if set
            if int(inv['invoice_number']) in category_overrides:
                override_val = category_overrides[int(inv['invoice_number'])]
                if override_val.strip().upper() in ["ENVIO LOCAL", "ENVÍO LOCAL"]:
                    override_val = "LOCAL"
                inv['shipping_type'] = override_val
            inv_num_str = str(inv['invoice_number'])
            order = factura_to_order.get(inv_num_str)
            
            status = order.get('status') if order else None
            inv['recibido'] = "X" if status in [OrderStatus.READY.value, OrderStatus.SHIPPED.value] else ""
            inv['entrega'] = "X" if status == OrderStatus.SHIPPED.value else ""
            
            pay_term = inv.get('payment_terms', '').upper()
            inv['credito'] = "X" if pay_term != 'CONTADO' else ""
            inv['pagado'] = "X" if float(inv.get('paid_to_date', 0)) >= float(inv.get('total', 0)) and float(inv.get('total', 0)) > 0 else ""
            
            inv['nota'] = order.get('observaciones', '') if order and order.get('observaciones') else (inv.get('shipping_type') or 'LOCAL')

            # Combined factura/pedido number for Excel
            order_num = inv.get('order_number', '')
            if order_num:
                inv['factura_pedido'] = f"{inv['invoice_number']}/{order_num}"
            else:
                inv['factura_pedido'] = str(inv['invoice_number'])

            st = (inv.get('shipping_type') or 'LOCAL').upper()
            if 'GDL' in st:
                gdl_inv.append(inv)
            elif 'MTY' in st:
                mty_inv.append(inv)
            elif 'IRA' in st:
                ira_inv.append(inv)
            elif 'FLETE' in st:
                flete_inv.append(inv)
            elif 'PAQUETERIA' in st or 'PAQUETERÍA' in st:
                paqueteria_inv.append(inv)
            else:
                # LOCAL and any other unknown shipping types go here
                locals_inv.append(inv)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Relacion de Envios"

        title_font = Font(bold=True, size=16)
        bold_font = Font(bold=True)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        right_align = Alignment(horizontal="right", vertical="center", wrap_text=True)
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

        gray_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
        dark_gray_fill = PatternFill(start_color="808080", end_color="808080", fill_type="solid")

        def style_cell(cell, font=None, alignment=None, border=None, fill=None):
            if font: cell.font = font
            if alignment: cell.alignment = alignment
            if border: cell.border = border
            if fill: cell.fill = fill
            
        def style_range(ws_obj, cell_range, font=None, alignment=None, border=None, fill=None):
            for row in ws_obj[cell_range]:
                for cell in row:
                    if font: cell.font = font
                    if alignment: cell.alignment = alignment
                    if border: cell.border = border
                    if fill: cell.fill = fill

        def apply_page_settings(ws_obj):
            from openpyxl.worksheet.page import PageMargins
            ws_obj.page_setup.orientation = "landscape"
            ws_obj.page_setup.paperSize = 1  # 1 = Letter
            ws_obj.page_setup.fitToWidth = 1
            ws_obj.page_setup.fitToHeight = 0
            ws_obj.sheet_properties.pageSetUpPr.fitToPage = True
            ws_obj.page_margins = PageMargins(left=0.25, right=0.25, top=0.5, bottom=0.5, header=0.3, footer=0.3)

        def write_invoices(ws_obj, start_row, inv_list, min_rows=10):
            r = start_row
            for inv in inv_list:
                # Format dates to DD/MM/YYYY if they exist
                f_ped = ""
                if inv.get('order_date'):
                    try:
                        f_ped = datetime.datetime.strptime(inv['order_date'][:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                    except:
                        f_ped = inv['order_date']

                f_fac = ""
                if inv.get('invoice_date'):
                    try:
                        f_fac = datetime.datetime.strptime(inv['invoice_date'][:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                    except:
                        f_fac = inv['invoice_date']

                data = [
                    f_ped,
                    inv.get('order_number', ''),
                    f_fac,
                    inv.get('invoice_number', ''),
                    inv.get('customer_name', ''),
                    inv.get('total', 0),
                    inv.get('nota', ''),
                    inv.get('credito', ''),
                    inv.get('pagado', ''),
                    inv.get('recibido', ''),
                    inv.get('entrega', '')
                ]
                for c_idx, val in enumerate(data, 1):
                    cell = ws_obj.cell(row=r, column=c_idx, value=val)
                    style_cell(cell, font=bold_font if c_idx == 7 else None, 
                               alignment=center_align if c_idx in [1, 2, 3, 4, 8, 9, 10, 11] else left_align, 
                               border=thin_border)
                    if c_idx == 6: # Importe
                        cell.number_format = '$#,##0.00'
                
                # Set row height to double (approx 28) to fit wrapped text
                ws_obj.row_dimensions[r].height = 28
                r += 1

            rows_written = len(inv_list)
            while rows_written < min_rows:
                for c_idx in range(1, 12):
                    style_cell(ws_obj.cell(row=r, column=c_idx, value=""), border=thin_border)
                r += 1
                rows_written += 1
            return r

        def setup_sheet_header(ws_obj, display_date, title="RELACIÓN DE ENVÍOS"):
            # Row 1
            ws_obj.merge_cells("C1:G1")
            cell = ws_obj.cell(row=1, column=3, value=title)
            style_cell(cell, font=title_font, alignment=center_align, border=thin_border)
            style_range(ws_obj, "C1:G1", border=thin_border)

            ws_obj.merge_cells("H1:I1")
            style_range(ws_obj, "H1:I1", border=thin_border)

            ws_obj.merge_cells("J1:K1")
            cell = ws_obj.cell(row=1, column=10, value="QB-IT-VE-01-F06")
            style_cell(cell, alignment=center_align, border=thin_border)
            style_range(ws_obj, "J1:K1", border=thin_border)

            # Row 2
            cell = ws_obj.cell(row=2, column=3, value="Fecha:")
            style_cell(cell, font=bold_font, alignment=center_align, border=thin_border, fill=gray_fill)

            ws_obj.merge_cells("D2:G2")
            cell = ws_obj.cell(row=2, column=4, value=display_date)
            style_cell(cell, font=bold_font, alignment=center_align, border=thin_border, fill=gray_fill)
            style_range(ws_obj, "D2:G2", border=thin_border)

            ws_obj.merge_cells("H2:I2")
            cell = ws_obj.cell(row=2, column=8, value="Crédito y Cobranza")
            style_cell(cell, font=bold_font, alignment=center_align, border=thin_border, fill=gray_fill)
            style_range(ws_obj, "H2:I2", border=thin_border)

            ws_obj.merge_cells("J2:K2")
            cell = ws_obj.cell(row=2, column=10, value="Almacén y Logística")
            style_cell(cell, font=bold_font, alignment=center_align, border=thin_border, fill=gray_fill)
            style_range(ws_obj, "J2:K2", border=thin_border)

            # Row 3 (Headers)
            headers = ["Fecha de\nPedido", "No. de\nPedido", "Fecha de\nFacturación", "No. de\nFactura", "Cliente", "Importe", "Observación", "Crédito", "Pagado", "Recibido", "Entrega"]
            for i, h in enumerate(headers, 1):
                cell = ws_obj.cell(row=3, column=i, value=h)
                style_cell(cell, font=bold_font, alignment=center_align, border=thin_border, fill=gray_fill)

            return 4

        def set_col_widths(ws_obj):
            ws_obj.column_dimensions['A'].width = 12
            ws_obj.column_dimensions['B'].width = 12
            ws_obj.column_dimensions['C'].width = 12
            ws_obj.column_dimensions['D'].width = 12
            ws_obj.column_dimensions['E'].width = 40
            ws_obj.column_dimensions['F'].width = 15
            ws_obj.column_dimensions['G'].width = 25
            ws_obj.column_dimensions['H'].width = 10
            ws_obj.column_dimensions['I'].width = 10
            ws_obj.column_dimensions['J'].width = 10
            ws_obj.column_dimensions['K'].width = 10

        # Format display date as DD/MM/YYYY for the Excel header
        if date_filter:
            try:
                parsed_date = datetime.datetime.strptime(date_filter, "%Y-%m-%d")
                display_date = parsed_date.strftime("%d/%m/%Y")
            except ValueError:
                display_date = date_filter
        else:
            display_date = datetime.datetime.now().strftime("%d/%m/%Y")


        # --- SHEET 1: LOCAL & PAQUETERIA ---
        ws.title = "Relacion de Envios"
        apply_page_settings(ws)
        row_idx = setup_sheet_header(ws, display_date)
        
        # LOCAL
        row_idx = write_invoices(ws, row_idx, locals_inv, min_rows=12)

        # PAQUETERIA Separator
        for col_idx in range(1, 12):
            style_cell(ws.cell(row=row_idx, column=col_idx), fill=dark_gray_fill, border=thin_border)
        row_idx += 1
        
        # PAQUETERIA
        row_idx = write_invoices(ws, row_idx, paqueteria_inv, min_rows=15)

        # FLETE INTERNO
        if flete_inv:
            # FLETE INTERNO Separator
            for col_idx in range(1, 12):
                style_cell(ws.cell(row=row_idx, column=col_idx), fill=dark_gray_fill, border=thin_border)
            row_idx += 1
            row_idx = write_invoices(ws, row_idx, flete_inv, min_rows=3)

        # End Separator
        for col_idx in range(1, 12):
            style_cell(ws.cell(row=row_idx, column=col_idx), fill=dark_gray_fill, border=thin_border)
        row_idx += 1
        
        # Extra empty row for aesthetic matching
        for col_idx in range(1, 12):
            style_cell(ws.cell(row=row_idx, column=col_idx), border=thin_border)

        set_col_widths(ws)

        # --- SHEET 2: GDL ---
        if gdl_inv:
            ws_gdl = wb.create_sheet("GDL")
            apply_page_settings(ws_gdl)
            row_idx = setup_sheet_header(ws_gdl, display_date, title="ANEXADAS GDL")
            row_idx = write_invoices(ws_gdl, row_idx, gdl_inv, min_rows=10)
            set_col_widths(ws_gdl)

        # --- SHEET 3: MTY ---
        if mty_inv:
            ws_mty = wb.create_sheet("MTY")
            apply_page_settings(ws_mty)
            row_idx = setup_sheet_header(ws_mty, display_date, title="ANEXADAS MTY")
            row_idx = write_invoices(ws_mty, row_idx, mty_inv, min_rows=10)
            set_col_widths(ws_mty)

        # --- SHEET 4: IRA ---
        if ira_inv:
            ws_ira = wb.create_sheet("IRAPUATO")
            apply_page_settings(ws_ira)
            row_idx = setup_sheet_header(ws_ira, display_date, title="ANEXADAS IRAPUATO")
            row_idx = write_invoices(ws_ira, row_idx, ira_inv, min_rows=10)
            set_col_widths(ws_ira)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"Facturas_{display_date.replace('/', '-')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f"Facturas Excel Export error: {e}")
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/api/facturas/export/custom", methods=["POST"])
@login_required
def api_facturas_export_custom():  # pragma: no cover
    data = request.get_json() or {}
    date_filter = data.get('date', datetime.datetime.now().strftime("%Y-%m-%d"))
    groups = data.get('groups', [])
    
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        import io
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Relacion de Envios"
        
        from openpyxl.worksheet.page import PageMargins
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = 1  # 1 = Letter
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins = PageMargins(left=0.25, right=0.25, top=0.5, bottom=0.5, header=0.3, footer=0.3)

        title_font = Font(bold=True, size=16)
        bold_font = Font(bold=True)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        gray_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
        dark_gray_fill = PatternFill(start_color="808080", end_color="808080", fill_type="solid")

        # Set up header
        # Row 1
        ws.merge_cells("C1:E1")
        cell = ws.cell(row=1, column=3, value="RELACIÓN DE ENVÍOS")
        cell.font = title_font
        cell.alignment = center_align
        cell.border = thin_border
        
        ws.merge_cells("H1:I1")
        cell = ws.cell(row=1, column=8, value="QB-IT-VE-01-F06")
        cell.alignment = center_align
        cell.border = thin_border
        
        # Format borders for merged cells
        for r in ws["C1:E1"]:
            for c in r: c.border = thin_border
        for r in ws["H1:I1"]:
            for c in r: c.border = thin_border

        # Row 2
        try:
            display_date = datetime.datetime.strptime(date_filter, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            display_date = date_filter
            
        cell = ws.cell(row=2, column=3, value="Fecha:")
        cell.font = bold_font
        cell.alignment = center_align
        cell.border = thin_border
        cell.fill = gray_fill
        
        ws.merge_cells("D2:E2")
        cell = ws.cell(row=2, column=4, value=display_date)
        cell.font = bold_font
        cell.alignment = center_align
        cell.border = thin_border
        cell.fill = gray_fill
        for r in ws["D2:E2"]:
            for c in r: c.border, c.fill = thin_border, gray_fill
            
        ws.merge_cells("F2:G2")
        cell = ws.cell(row=2, column=6, value="Crédito y Cobranza")
        cell.font = bold_font
        cell.alignment = center_align
        cell.border = thin_border
        cell.fill = gray_fill
        for r in ws["F2:G2"]:
            for c in r: c.border, c.fill = thin_border, gray_fill
            
        ws.merge_cells("H2:I2")
        cell = ws.cell(row=2, column=8, value="Almacén y Logística")
        cell.font = bold_font
        cell.alignment = center_align
        cell.border = thin_border
        cell.fill = gray_fill
        for r in ws["H2:I2"]:
            for c in r: c.border, c.fill = thin_border, gray_fill

        # Row 3
        headers = ["No. Ordn Vnt", "No.Fact", "Cliente", "Importe", "Observación", "Crédito", "Pagado", "Recibido", "Entrega"]
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=3, column=i, value=h)
            c.font = bold_font
            c.alignment = center_align
            c.border = thin_border
            c.fill = gray_fill
            
        # Write rows
        row_idx = 4
        for idx, g in enumerate(groups):
            if idx > 0:
                # separator
                for col_idx in range(1, 10):
                    c = ws.cell(row=row_idx, column=col_idx)
                    c.fill = dark_gray_fill
                    c.border = thin_border
                row_idx += 1
                
            for inv in g.get('invoices', []):
                # Format money
                total = float(inv.get('total') or 0)
                
                # Check for custom customer name
                cust_name = inv.get('customer_name', '')
                if inv.get('_temp_customer'):
                    cust_name = inv.get('_temp_customer')
                    
                pay_term = inv.get('payment_terms', '').upper()
                is_credito = "X" if pay_term != 'CONTADO' else ""
                
                try:
                    paid = float(inv.get('paid_to_date') or 0)
                    tot = float(inv.get('total') or 0)
                    is_pagado = "X" if paid >= tot and tot > 0 else ""
                except ValueError:
                    is_pagado = ""

                data = [
                    inv.get('order_number', ''),
                    inv.get('invoice_number', ''),
                    cust_name,
                    total,
                    inv.get('observaciones') or inv.get('shipping_type') or 'LOCAL',
                    is_credito,
                    is_pagado,
                    "X" if inv.get('recibido') else "",
                    "X" if inv.get('entrega') else ""
                ]
                
                for c_idx, val in enumerate(data, 1):
                    c = ws.cell(row=row_idx, column=c_idx, value=val)
                    c.border = thin_border
                    if c_idx == 4:
                        c.number_format = '$#,##0.00'
                    if c_idx == 5:
                        c.font = bold_font
                        
                    if c_idx in [1, 2, 6, 7, 8, 9]:
                        c.alignment = center_align
                    else:
                        c.alignment = left_align
                        
                # Set row height to double (approx 28) to fit wrapped text
                ws.row_dimensions[row_idx].height = 28
                row_idx += 1
                
        # Empty rows at the end to match layout
        for empty_row in range(3):
            for col_idx in range(1, 10):
                ws.cell(row=row_idx, column=col_idx).border = thin_border
            row_idx += 1

        # Widths
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 40
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 20
        ws.column_dimensions['F'].width = 10
        ws.column_dimensions['G'].width = 10
        ws.column_dimensions['H'].width = 12
        ws.column_dimensions['I'].width = 12

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"Relacion_Envios_{display_date.replace('/', '-')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        logging.error(f"Facturas Custom Export error: {e}")
        return jsonify({"error": str(e)}), 500



@orders_bp.route("/api/facturas/<int:invoice_number>/toggle", methods=["POST"])
@login_required
def toggle_factura_status(invoice_number):  # pragma: no cover
    """Toggle Recibido or Entrega checkbox from the Facturas tab, which updates the related order status."""
    if not current_user.can_edit_facturas():
        return jsonify({"error": "Sin permisos"}), 403

    data = request.get_json() or {}
    field = data.get("field") # 'recibido' or 'entrega'
    value = data.get("value") # boolean

    if field not in ['recibido', 'entrega', 'observaciones']:
        return jsonify({"error": "Campo inválido"}), 400
        
    new_status = None

    order_mgr = current_app.order_status_mgr
    # Find related order
    related_order = next((o for o in order_mgr.orders.values() if o.get("factura_number") == str(invoice_number)), None)

    if not related_order:
        return jsonify({"error": "No se encontró un pedido local vinculado a esta factura"}), 404

    order_id = related_order['order_id']
    current_status = related_order.get('status')

    if field == 'recibido':
        new_status = OrderStatus.READY.value if value else OrderStatus.INVOICING.value
    elif field == 'entrega':
        if value:
            # Can only jump to Enviado if it was at least at Relacion de envio
            new_status = OrderStatus.SHIPPED.value
        else:
            new_status = OrderStatus.READY.value
    elif field == 'observaciones':
        related_order['observaciones'] = str(value)
        order_mgr.save_database()
        return jsonify({"success": True})

    success = order_mgr.update_status(
        order_id, new_status, current_user.username, notes=f"Actualizado desde checkbox '{field}' en tablero de Facturas"
    )

    if success:
        try:
            updated_order = order_mgr.get_order(order_id)
            _publish_event({
                "type": "order_updated",
                "order_id": str(order_id),
                "order": updated_order,
            })
            if current_status != new_status:
                _publish_event({
                    "type": "status_changed",
                    "order_id": str(order_id),
                    "customer": related_order.get("customer_name", ""),
                    "from": current_status,
                    "to": new_status
                })
        except Exception as e:
            current_app.logger.warning(f"Ignored exception: {e}")
        return jsonify({"success": True, "new_status": new_status})
    
    return jsonify({"error": "Error al actualizar estado"}), 500
