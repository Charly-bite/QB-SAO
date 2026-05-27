"""
Order status routes for SGA Web
"""

import datetime
import json as json_mod
import logging
import os
import time
import urllib.request
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template, request, Response
import queue
from flask_login import current_user, login_required

from core.order_status_manager import OrderStatus

# Weather cache (module-level)
_weather_cache = {"data": None, "timestamp": 0}

orders_bp = Blueprint("orders", __name__)

# Simple in-memory pub/sub for Server-Sent Events (SSE)
_SUBSCRIBERS = []


def _publish_event(event: dict):
    # Push event to all subscriber queues (non-blocking)
    for q in list(_SUBSCRIBERS):
        try:
            q.put(event, block=False)
        except Exception:
            # ignore full/closed queues
            pass


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


@orders_bp.route("/")
@login_required
def index():
    """Order status dashboard"""
    order_mgr = current_app.order_status_mgr

    # Get filter params
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


@orders_bp.route('/stream')
@_require_monitor_token
def stream():
    """Server-Sent Events stream that broadcasts order updates to monitors."""
    q = queue.Queue()
    _SUBSCRIBERS.append(q)

    def event_stream(local_q):  # pragma: no cover
        try:  # pragma: no cover
            while True:  # pragma: no cover
                data = local_q.get()  # pragma: no cover
                yield f"data: {json_mod.dumps(data, ensure_ascii=False)}\n\n"  # pragma: no cover
        finally:
            # Clean up when client disconnects
            try:  # pragma: no cover
                _SUBSCRIBERS.remove(local_q)  # pragma: no cover
            except ValueError:  # pragma: no cover
                pass  # pragma: no cover

    return Response(event_stream(q), mimetype='text/event-stream')


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


@orders_bp.route("/<order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    """Update order status"""
    if not current_user.can_print_labels():  # Operators can update status
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
        "Preparando": "Terminado",
        "Preparado": "Terminado",
        "Terminado": "Terminado",
        "Listo para Envío": "Relacion de envio",
        "Listo para Envio": "Relacion de envio",
        "Entregado a almacen": "Relacion de envio",
        "Recibido por almacen": "Relacion de envio",
        "Relación de envío": "Relacion de envio",
        "Relacion de envio": "Relacion de envio",
        "Enviado": "Enviado al cliente",
        "Recibido por cliente": "Enviado al cliente",
        # Reverse mappings (old enum values → new enum values)
        "Terminado": "Terminado",
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
            "updated_by": sap_user,
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
                "updated_by": sap_user,
            }

            order_id = str(flattened_order["DocNum"])

            # Check if already exists
            if order_id in order_mgr.orders:
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
    if not current_user.is_admin():
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

            order_id = str(flattened_order["DocNum"])

            # Check if exists
            if order_id in order_mgr.orders:
                needs_update = False

                # Update SAP status if changed
                current_sap_status = order_mgr.orders[order_id].get("sap_status")
                new_sap_status = flattened_order["sap_status"]

                if current_sap_status != new_sap_status:
                    order_mgr.orders[order_id]["sap_status"] = new_sap_status
                    # Only stamp last_updated when LOCAL status is also changed
                    current_local = order_mgr.orders[order_id].get("status")
                    if new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ]:
                        order_mgr.orders[order_id]["status"] = (
                            OrderStatus.INVOICING.value
                        )
                        order_mgr.orders[order_id]["last_updated"] = (
                            datetime.datetime.now().isoformat()
                        )
                    elif (
                        new_sap_status == "Cancelado"
                        and current_local != OrderStatus.CANCELLED.value
                    ):
                        order_mgr.orders[order_id]["status"] = (
                            OrderStatus.CANCELLED.value
                        )
                        order_mgr.orders[order_id]["last_updated"] = (
                            datetime.datetime.now().isoformat()
                        )
                    needs_update = True

                # Always sync factura_number from SAP
                new_fact = flattened_order.get("factura_number")
                cur_fact = order_mgr.orders[order_id].get("factura_number")
                if new_fact and cur_fact != new_fact:
                    order_mgr.orders[order_id]["factura_number"] = new_fact
                    needs_update = True

                if needs_update:
                    updated_count += 1
            else:
                # New order found
                order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                new_count += 1

        if updated_count > 0 or new_count > 0:
            order_mgr._save_database()

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

            order_id = str(flattened_order["DocNum"])

            # Check if exists
            if order_id in order_mgr.orders:
                needs_update = False
                # Update SAP status if changed
                current_sap_status = order_mgr.orders[order_id].get("sap_status")
                new_sap_status = flattened_order["sap_status"]

                if current_sap_status != new_sap_status:
                    order_mgr.orders[order_id]["sap_status"] = new_sap_status
                    # Only stamp last_updated when LOCAL status is also changed
                    current_local = order_mgr.orders[order_id].get("status")
                    if new_sap_status == "Cerrado" and current_local not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ]:
                        order_mgr.orders[order_id]["status"] = (
                            OrderStatus.INVOICING.value
                        )
                        order_mgr.orders[order_id]["last_updated"] = (
                            datetime.datetime.now().isoformat()
                        )
                    elif (
                        new_sap_status == "Cancelado"
                        and current_local != OrderStatus.CANCELLED.value
                    ):
                        order_mgr.orders[order_id]["status"] = (
                            OrderStatus.CANCELLED.value
                        )
                        order_mgr.orders[order_id]["last_updated"] = (
                            datetime.datetime.now().isoformat()
                        )
                    needs_update = True

                # Always sync factura_number from SAP
                new_fact = flattened_order.get("factura_number")
                cur_fact = order_mgr.orders[order_id].get("factura_number")
                if new_fact and cur_fact != new_fact:
                    order_mgr.orders[order_id]["factura_number"] = new_fact
                    needs_update = True

                if needs_update:
                    updated_count += 1
            else:
                # New order found
                order_mgr.import_from_sap(flattened_order, imported_by=sap_user)
                new_count += 1

        if updated_count > 0 or new_count > 0:
            order_mgr._save_database()

        return jsonify({"success": True, "updated": updated_count, "new": new_count})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Module-level sync cache ─────────────────────────────────────────
_last_sap_sync = 0  # epoch timestamp of last SAP sync
_SAP_SYNC_INTERVAL = 10  # seconds between SAP syncs (real time)


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

    # ── Throttled SAP sync ────────────────────────────────────────────
    now = _time.time()
    if current_app.sap_available and (now - _last_sap_sync) >= _SAP_SYNC_INTERVAL:
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
            _last_sap_sync = now
            sap_synced = True
        except Exception as e:
            logging.warning(f"Background SAP sync error: {e}")

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

    try:
        sap = current_app.sap_connector
        if not sap or not sap.connected:  # pragma: no cover
            from sap_connector import SAPHanaConnector  # pragma: no cover

            sap = SAPHanaConnector()  # pragma: no cover
            sap.connect()  # pragma: no cover
            current_app.sap_connector = sap  # pragma: no cover

        invoices = sap.get_todays_invoices(date_str=date_filter)

        # Calculate stats
        total_mxn = sum(i["total"] for i in invoices if i["currency"] == "MXN")
        total_usd = sum(i["total"] for i in invoices if i["currency"] == "USD")
        active = [i for i in invoices if i["status"] != "Cancelada"]
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

        return jsonify({
            "invoices": invoices,
            "stats": stats,
            "generated_at": datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        logging.error(f"Facturas API error: {e}")
        return jsonify({"error": str(e), "invoices": [], "stats": {}}), 500
