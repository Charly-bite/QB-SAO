#!/usr/bin/env python3
"""
Order Status Manager — Open-OMS
Manages a local database of order statuses.

Database strategy:
- READ from existing 'order_status' table (populated by SGA_dev)
- WRITE to 'seguimiento_order_status' table (this app's own tracking)
"""

import datetime
import json
import logging
import os
import tempfile
import time
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATUS_LABEL_MIGRATIONS = {
    "Preparando": "Entregado",
    "Preparado": "Entregado",
    "Terminado": "Entregado",
    "Listo para Envío": "Relacion de envio",
    "Listo para Envio": "Relacion de envio",
    "Entregado a almacen": "Relacion de envio",
    "Recibido por almacen": "Relacion de envio",
    "Relación de envío": "Relacion de envio",
    "Enviado": "Enviado al cliente",
    "Recibido por cliente": "Enviado al cliente",
}


class OrderStatus(Enum):
    """Possible order statuses"""

    PENDING = "Pendiente"
    IN_PROGRESS = "En Proceso"
    PICKING = "Entregado"
    INVOICING = "Facturacion"
    READY = "Relacion de envio"
    SHIPPED = "Enviado al cliente"
    CANCELLED = "Cancelado"
    ON_HOLD = "En Espera"


class OrderStatusManager:
    """
    Manages order status tracking for Open-OMS.

    Database strategy:
    - Reads from SGA's 'order_status' table as base data
    - Writes its own tracking to 'seguimiento_order_status' table
    - Falls back to local JSON file when SQL is unavailable
    """

    # The table this app WRITES to
    WRITE_TABLE = "seguimiento_order_status"
    # The table SGA_dev writes to (read-only for us)
    READ_TABLE = "order_status"

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Store runtime data in project-root /data/, not inside the source /core/ dir
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "order_status_db.json")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self.orders: Dict[str, Dict[str, Any]] = {}

        # Connect to DB
        from core.database_client import DatabaseClient

        self.db_client = DatabaseClient()
        self.sql_engine = None
        try:
            if self.db_client.connect():
                self.sql_engine = self.db_client.get_sql_engine()  # pragma: no cover
        except Exception as e:  # pragma: no cover
            logger.warning(f"[WARN] OrderStatusManager DB error: {e}")  # pragma: no cover

        # Debounce tracking for _save_database
        self._last_save_time = 0.0
        self._dirty = False
        self._SAVE_DEBOUNCE_SECONDS = 5

        self._last_load_time = 0.0
        self._LOAD_THROTTLE_SECONDS = 5.0

        self._ensure_db_table_exists()
        self._load_database()

    def _ensure_db_table_exists(self):
        """Creates the seguimiento_order_status table if it does not exist."""
        if not self.sql_engine:
            return
        try:
            with self.sql_engine.begin() as conn:
                conn.exec_driver_sql(f"""
                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.WRITE_TABLE}' and xtype='U')
                    CREATE TABLE {self.WRITE_TABLE} (
                        order_id VARCHAR(50) PRIMARY KEY,
                        status VARCHAR(100),
                        last_updated VARCHAR(50),
                        data NVARCHAR(MAX)
                    )
                """)
        except Exception as e:
            logger.warning(f"[WARN] Could not ensure {self.WRITE_TABLE} table exists: {e}")

    def _load_database(self):
        """
        Load order status database.
        First tries to load from our own write table.
        If empty, seeds from SGA's read table.
        Falls back to JSON on disk.
        """
        loaded_from_sql = False

        if self.sql_engine:  # pragma: no cover
            try:
                import pandas as pd

                # 1. Load from our own write table first
                df = pd.read_sql(
                    f"SELECT * FROM {self.WRITE_TABLE}", con=self.sql_engine
                )
                if len(df) > 0:
                    new_orders = {}
                    for _, row in df.iterrows():
                        o_id = str(row["order_id"])
                        try:
                            order_data = json.loads(str(row["data"]))
                            if order_data.get("customer_code") != "CL1662":
                                new_orders[o_id] = order_data
                        except Exception:
                            pass
                    self.orders = new_orders
                    loaded_from_sql = True
                    logger.warning(
                        f"[OK] Loaded {len(self.orders)} orders from {self.WRITE_TABLE}"
                    )
                else:
                    # 2. Seed from SGA's read table
                    try:
                        df_sga = pd.read_sql(
                            f"SELECT * FROM {self.READ_TABLE}", con=self.sql_engine
                        )
                        if len(df_sga) > 0:
                            new_orders = {}
                            for _, row in df_sga.iterrows():
                                o_id = str(row["order_id"])
                                try:
                                    order_data = json.loads(str(row["data"]))
                                    if order_data.get("customer_code") != "CL1662":
                                        new_orders[o_id] = order_data
                                except Exception:
                                    pass
                            self.orders = new_orders
                            loaded_from_sql = True
                            logger.warning(
                                f"[OK] Seeded {len(self.orders)} orders from {self.READ_TABLE} → {self.WRITE_TABLE}"
                            )
                            # Save to our own table immediately
                            self._save_database()
                    except Exception as e:
                        logger.warning(f"[WARN] Could not seed from {self.READ_TABLE}: {e}")

            except Exception as e:
                logger.warning(f"[WARN] Error loading from SQL: {e}")

        if not loaded_from_sql:
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_orders = data.get("orders", {})
                        self.orders = {
                            k: v for k, v in raw_orders.items()
                            if v.get("customer_code") != "CL1662"
                        }
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"[WARN] Error loading order status database: {e}")
                    self.orders = {}
            else:
                self.orders = {}

        changed = self._normalize_status_labels()
        if changed:
            self._save_database()

        import time
        self._last_load_time = time.time()

    def _normalize_order_labels(self, order: Dict[str, Any]) -> bool:
        """Normalize legacy status labels for a single order in place."""
        changed = False
        status = order.get("status")
        if status in STATUS_LABEL_MIGRATIONS:
            order["status"] = STATUS_LABEL_MIGRATIONS[status]
            changed = True

        history = order.get("status_history", [])
        for entry in history:
            entry_status = entry.get("status")
            if entry_status in STATUS_LABEL_MIGRATIONS:
                entry["status"] = STATUS_LABEL_MIGRATIONS[entry_status]
                changed = True

            prev_status = entry.get("previous_status")
            if prev_status in STATUS_LABEL_MIGRATIONS:
                entry["previous_status"] = STATUS_LABEL_MIGRATIONS[prev_status]
                changed = True
        return changed

    def _normalize_status_labels(self) -> bool:
        """Normalize legacy status labels to the current naming in memory."""
        changed = False
        for order in self.orders.values():
            if self._normalize_order_labels(order):
                changed = True

        return changed

    def reload_if_needed(self, force=False):
        """Reload the database if throttled time elapsed or forced."""
        import time
        now = time.time()
        if force or (now - getattr(self, "_last_load_time", 0.0)) > getattr(self, "_LOAD_THROTTLE_SECONDS", 5.0):
            self._load_database()

    # SQL MERGE template — used by both _save_database() and _save_order().
    # MERGE avoids TRUNCATE so concurrent writers never erase each other's data.
    _MERGE_SQL_TMPL = """
        MERGE {table} AS target
        USING (VALUES (?, ?, ?, ?)) AS source
            (order_id, status, last_updated, data)
        ON target.order_id = source.order_id
        WHEN MATCHED THEN UPDATE SET
            status       = source.status,
            last_updated = source.last_updated,
            data         = source.data
        WHEN NOT MATCHED THEN INSERT
            (order_id, status, last_updated, data)
            VALUES (source.order_id, source.status,
                    source.last_updated, source.data);
    """

    def _save_database(self, force=False):
        """Persist all in-memory orders to SQL (MERGE) and JSON.

        JSON writes are atomic (write to temp file, then os.replace).
        SQL uses MERGE so concurrent writers never truncate each other's rows.
        """
        last_updated = datetime.datetime.now().isoformat()


        # Persist to SQL via MERGE (no TRUNCATE — safe for concurrent writers)
        if self.sql_engine:
            try:
                records = [
                    (
                        str(o_id),
                        o_data.get("status", ""),
                        o_data.get("last_updated", last_updated),
                        json.dumps(o_data, ensure_ascii=False),
                    )
                    for o_id, o_data in list(self.orders.items())
                ]
                if records:
                    merge_sql = self._MERGE_SQL_TMPL.format(table=self.WRITE_TABLE)
                    with self.sql_engine.begin() as conn:
                        # Passing the entire list to exec_driver_sql performs an executemany
                        conn.exec_driver_sql(merge_sql, records)
            except Exception as e:  # pragma: no cover
                import traceback
                logger.warning(f"[WARN] Error saving to SQL: {e}")
                traceback.logger.warning_exc()

        # Fallback / sync to JSON (atomic write)
        try:
            data = {"orders": self.orders, "last_updated": last_updated}
            dir_name = os.path.dirname(self.db_path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.db_path)
            except Exception:  # pragma: no cover
                # Always clean up the temp file so we never leave orphans on disk
                try:  # pragma: no cover
                    os.unlink(tmp_path)  # pragma: no cover
                except OSError:  # pragma: no cover
                    pass  # pragma: no cover
                raise  # pragma: no cover
            self._last_save_time = time.time()
            self._dirty = False
            return True
        except Exception as e:
            logger.warning(f"[WARN] Error saving to JSON: {e}")
            return False

    def _save_order(self, order_id: str) -> bool:
        """Persist a single order to SQL via MERGE without rewriting the whole table.

        This is the preferred method for hot-path writes (status updates, webhook
        callbacks) because it targets exactly one row and is safe against concurrent
        writers.  Falls back to a double _save_database() if SQL is unavailable.
        The JSON file is marked dirty and will be flushed on the next debounced save.
        """
        order_id = str(order_id)
        if order_id not in self.orders:  # pragma: no cover
            return False

        o_data = self.orders[order_id]

        if not self.sql_engine:
            # No SQL connection — fall through to a full JSON save
            return self._save_database(force=True)

        try:  # pragma: no cover
            record = (
                order_id,
                o_data.get("status", ""),
                o_data.get("last_updated", ""),
                json.dumps(o_data, ensure_ascii=False),
            )
            merge_sql = self._MERGE_SQL_TMPL.format(table=self.WRITE_TABLE)
            with self.sql_engine.begin() as conn:
                conn.exec_driver_sql(merge_sql, record)
            # Mark JSON as dirty; it will be flushed on the next debounced save
            self._dirty = True
            return True
        except Exception as e:  # pragma: no cover
            logger.warning(f"[WARN] _save_order({order_id}) failed: {e}")
            # Fallback: full save so at least JSON stays consistent
            return self._save_database(force=True)

    def import_from_sap(
        self, sap_order: Dict[str, Any], imported_by: str = "system", save: bool = True
    ) -> Dict[str, Any]:
        """Import an order from SAP data without modifying SAP."""
        self.reload_if_needed(force=True)

        order_id = str(sap_order.get("DocNum", sap_order.get("order_id", "")))

        if not order_id:
            raise ValueError("Order must have a DocNum or order_id")

        existing_status = None
        existing_history = []
        existing_imported_at = datetime.datetime.now().isoformat()
        existing_last_updated = datetime.datetime.now().isoformat()

        existing_factura_number = None
        existing_delivery_number = None
        existing_doc_entry = None

        if order_id in self.orders:
            existing_status = self.orders[order_id].get("status")
            existing_history = self.orders[order_id].get("status_history", [])
            existing_imported_at = self.orders[order_id].get(
                "imported_at", existing_imported_at
            )
            existing_last_updated = self.orders[order_id].get(
                "last_updated", existing_last_updated
            )
            existing_factura_number = self.orders[order_id].get("factura_number")
            existing_delivery_number = self.orders[order_id].get("delivery_number")
            existing_doc_entry = self.orders[order_id].get("doc_entry")
            existing_shipping_type = self.orders[order_id].get("shipping_type", "LOCAL")
        else:
            existing_shipping_type = "LOCAL"

        doc_entry = sap_order.get("DocEntry", sap_order.get("doc_entry"))
        if doc_entry is not None:
            try:
                doc_entry = int(doc_entry)
            except (ValueError, TypeError):  # pragma: no cover
                doc_entry = None  # pragma: no cover
        else:
            doc_entry = existing_doc_entry

        order_record = {
            "order_id": order_id,
            "doc_entry": doc_entry,
            "customer_code": sap_order.get("CardCode", ""),
            "customer_name": sap_order.get("CardName", ""),
            "order_date": sap_order.get("DocDate", ""),
            "delivery_date": sap_order.get("DocDueDate", ""),
            "total": sap_order.get("DocTotal", 0),
            "currency": sap_order.get("DocCurrency", "MXN"),
            "comments": sap_order.get("Comments", ""),
            "items": sap_order.get("items", []),
            "sap_status": sap_order.get("sap_status", "Abierto"),
            "factura_number": sap_order.get("factura_number") or existing_factura_number,
            "delivery_number": sap_order.get("delivery_number") or existing_delivery_number,
            "status": existing_status or OrderStatus.PENDING.value,
            "status_history": existing_history,
            "imported_at": existing_imported_at,
            "last_updated": existing_last_updated,
            "updated_by": (
                sap_order.get("updated_by") or imported_by
                if not existing_status
                else self.orders.get(order_id, {}).get("updated_by", "system")
            ),
            "created_by": (
                sap_order.get("created_by") or sap_order.get("creator_name") or imported_by
                if not existing_status
                else self.orders.get(order_id, {}).get("created_by", "system")
            ),
            "shipping_type": sap_order.get("shipping_type") or existing_shipping_type,
        }

        if not existing_status:
            order_record["status_history"].append(
                {
                    "status": OrderStatus.PENDING.value,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "user": imported_by,
                    "notes": "Importado desde SAP",
                }
            )

        self.orders[order_id] = order_record
        if save:
            self._save_database()

        return order_record


    def bulk_import_from_sap(self, sap_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import multiple orders from SAP at once."""
        self.reload_if_needed(force=True)
        stats = {
            "total": len(sap_orders),
            "imported": 0,
            "updated": 0,
            "errors": 0,
            "error_details": [],
        }

        for sap_order in sap_orders:
            try:
                order_id = str(sap_order.get("header", {}).get("order_number", ""))
                if not order_id:
                    continue

                was_existing = order_id in self.orders
                creator = sap_order["header"].get("creator_name") or "system"

                order_data = {
                    "DocNum": sap_order["header"]["order_number"],
                    "DocEntry": sap_order["header"].get("doc_entry"),
                    "CardCode": sap_order["header"].get("customer_code", ""),
                    "CardName": sap_order["header"].get("customer_name", ""),
                    "DocDate": sap_order["header"].get("order_date", ""),
                    "DocDueDate": sap_order["header"].get("delivery_date", ""),
                    "DocTotal": sap_order["header"].get("total_value", 0),
                    "DocCurrency": sap_order["header"].get("currency", "MXN"),
                    "sap_status": sap_order["header"].get("sap_status", "Abierto"),
                    "factura_number": sap_order["header"].get("factura_number"),
                    "delivery_number": sap_order["header"].get("delivery_number"),
                    "items": sap_order.get("items", []),
                    "updated_by": sap_order["header"].get("updater_name") or "system_sync",
                    "created_by": creator,
                    "shipping_type": sap_order["header"].get("shipping_type", "LOCAL"),
                }

                self.import_from_sap(order_data, imported_by=creator, save=False)

                if was_existing:
                    stats["updated"] += 1
                else:
                    stats["imported"] += 1

            except Exception as e:
                stats["errors"] += 1
                stats["error_details"].append(
                    {
                        "order": str(
                            sap_order.get("header", {}).get("order_number", "unknown")
                        ),
                        "error": str(e),
                    }
                )

        self._save_database(force=True)
        return stats

    def update_status(
        self, order_id: str, new_status: str, user: str, notes: str = ""
    ) -> bool:
        """Update the status of an order."""
        order_id = str(order_id)

        if order_id not in self.orders:
            # Fallback to load/fetch if not in-memory
            if not self.get_order(order_id):
                logger.warning(f"[WARN] Order {order_id} not found")
                return False

        old_status = self.orders[order_id]["status"]
        now_iso = datetime.datetime.now().isoformat()

        self.orders[order_id]["status"] = new_status
        self.orders[order_id]["last_updated"] = now_iso
        self.orders[order_id]["updated_by"] = user

        self.orders[order_id]["status_history"].append(
            {
                "status": new_status,
                "previous_status": old_status,
                "timestamp": now_iso,
                "user": user,
                "notes": notes,
            }
        )

        # Use targeted single-row MERGE instead of full table rewrite
        return self._save_order(order_id)

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get a single order by ID."""
        self.reload_if_needed()
        order_id = str(order_id)
        if order_id in self.orders:
            return self.orders[order_id]

        if self.sql_engine:  # pragma: no cover
            try:
                with self.sql_engine.connect() as conn:
                    raw_conn = conn.connection
                    cursor = raw_conn.cursor()
                    cursor.execute(f"SELECT data FROM {self.WRITE_TABLE} WHERE order_id = ?", (order_id,))
                    row = cursor.fetchone()
                    cursor.close()
                    if row:
                        order_data = json.loads(row[0])
                        self._normalize_order_labels(order_data)
                        self.orders[order_id] = order_data
                        return order_data
            except Exception as e:
                logger.warning(f"[WARN] Error loading order {order_id} from SQL fallback: {e}")
        return None

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders sorted by last updated."""
        self.reload_if_needed()
        orders_list = list(self.orders.values())
        orders_list.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return orders_list

    def get_orders_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get orders filtered by status."""
        self.reload_if_needed()
        return [o for o in self.orders.values() if o.get("status") == status]

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """Get orders that are not shipped or cancelled."""
        self.reload_if_needed()
        inactive_statuses = []
        active = [
            o for o in self.orders.values() if o.get("status") not in inactive_statuses
        ]
        active.sort(key=lambda x: x.get("order_date", ""), reverse=True)
        return active

    def get_order_count_by_status(self) -> Dict[str, int]:
        """Get count of orders grouped by status."""
        self.reload_if_needed()
        counts = {}
        for status in OrderStatus:
            counts[status.value] = len(self.get_orders_by_status(status.value))
        return counts

    def reconcile_statuses(self) -> list:
        """Fix orders where sap_status and local status are out of sync. Returns list of changed orders."""
        changes = []
        now_iso = datetime.datetime.now().isoformat()

        for order_id, order in list(self.orders.items()):
            sap_status = order.get("sap_status", "")
            local_status = order.get("status", "")

            new_status = None
            if sap_status == "Cerrado":
                has_factura = bool(order.get("factura_number"))
                
                if has_factura:
                    # Si tiene factura, lo avanzamos hasta Facturación (si está atrasado)
                    if local_status not in [
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ]:
                        new_status = OrderStatus.INVOICING.value
                else:
                    # Si NO tiene factura, lo máximo automático es Terminado
                    if local_status not in [
                        OrderStatus.PICKING.value,
                        OrderStatus.INVOICING.value,
                        OrderStatus.READY.value,
                        OrderStatus.SHIPPED.value,
                    ]:
                        new_status = OrderStatus.PICKING.value
            elif (
                sap_status == "Cancelado"
                and local_status != OrderStatus.CANCELLED.value
            ):
                new_status = OrderStatus.CANCELLED.value

            if new_status:
                old_status = order["status"]
                order["status"] = new_status
                order["last_updated"] = now_iso
                order["status_history"].append(
                    {
                        "status": new_status,
                        "previous_status": old_status,
                        "timestamp": now_iso,
                        "user": "system",
                        "notes": f"Reconciliación automática: SAP={sap_status}",
                    }
                )
                changes.append({
                    "order_id": order_id,
                    "customer": order.get("customer_name", ""),
                    "from": old_status,
                    "to": new_status
                })

        if len(changes) > 0:
            self._save_database()

        return changes

    def delete_order(self, order_id: str) -> bool:
        """Delete an order from the local database."""
        order_id = str(order_id)
        if order_id in self.orders:
            del self.orders[order_id]
            # Issue a targeted DELETE instead of a full table rewrite
            if self.sql_engine:  # pragma: no cover
                try:
                    with self.sql_engine.connect() as conn:
                        raw_conn = conn.connection
                        cursor = raw_conn.cursor()
                        cursor.execute(
                            f"DELETE FROM {self.WRITE_TABLE} WHERE order_id = ?",
                            (order_id,),
                        )
                        raw_conn.commit()
                        cursor.close()
                except Exception as e:
                    logger.warning(f"[WARN] delete_order SQL failed for {order_id}: {e}")
            # Flush JSON to stay consistent
            return self._save_database(force=True)
        return False

    def get_status_options(self) -> List[str]:
        """Get list of available status options."""
        return [status.value for status in OrderStatus]

    def export_for_web(self) -> Dict[str, Any]:
        """Export order data for the web interface."""
        orders = self.get_all_orders()
        web_orders = []
        for order in orders:
            web_orders.append(
                {
                    "order_id": order.get("order_id"),
                    "customer_name": order.get("customer_name"),
                    "order_date": order.get("order_date"),
                    "delivery_date": order.get("delivery_date"),
                    "status": order.get("status"),
                    "last_updated": order.get("last_updated"),
                    "item_count": len(order.get("items", [])),
                }
            )

        return {
            "orders": web_orders,
            "status_counts": self.get_order_count_by_status(),
            "generated_at": datetime.datetime.now().isoformat(),
        }

