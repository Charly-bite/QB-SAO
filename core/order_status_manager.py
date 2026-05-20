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
import os
from enum import Enum
from typing import Any, Dict, List, Optional

STATUS_LABEL_MIGRATIONS = {
    "Preparando": "Terminado",
    "Preparado": "Terminado",
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
    PICKING = "Terminado"
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
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "order_status_db.json")

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
            print(f"⚠️ OrderStatusManager DB error: {e}")  # pragma: no cover

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
            print(f"⚠️ Could not ensure {self.WRITE_TABLE} table exists: {e}")

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
                    self.orders = {}
                    for _, row in df.iterrows():
                        o_id = str(row["order_id"])
                        try:
                            self.orders[o_id] = json.loads(str(row["data"]))
                        except Exception:
                            pass
                    loaded_from_sql = True
                    print(
                        f"✅ Loaded {len(self.orders)} orders from {self.WRITE_TABLE}"
                    )
                else:
                    # 2. Seed from SGA's read table
                    try:
                        df_sga = pd.read_sql(
                            f"SELECT * FROM {self.READ_TABLE}", con=self.sql_engine
                        )
                        if len(df_sga) > 0:
                            self.orders = {}
                            for _, row in df_sga.iterrows():
                                o_id = str(row["order_id"])
                                try:
                                    self.orders[o_id] = json.loads(str(row["data"]))
                                except Exception:
                                    pass
                            loaded_from_sql = True
                            print(
                                f"✅ Seeded {len(self.orders)} orders from {self.READ_TABLE} → {self.WRITE_TABLE}"
                            )
                            # Save to our own table immediately
                            self._save_database()
                    except Exception as e:
                        print(f"⚠️ Could not seed from {self.READ_TABLE}: {e}")

            except Exception as e:
                print(f"⚠️ Error loading from SQL: {e}")

        if not loaded_from_sql:
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.orders = data.get("orders", {})
                except (json.JSONDecodeError, IOError) as e:
                    print(f"⚠️ Error loading order status database: {e}")
                    self.orders = {}
            else:
                self.orders = {}

        changed = self._normalize_status_labels()
        if changed:
            self._save_database()

    def _normalize_status_labels(self) -> bool:
        """Normalize legacy status labels to the current naming in memory."""
        changed = False
        for order in self.orders.values():
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

    def _save_database(self):
        """Save the order status database to our own SQL table and disk."""
        last_updated = datetime.datetime.now().isoformat()

        # Save to SQL (our own table)
        if self.sql_engine:
            try:
                records = []
                for o_id, o_data in self.orders.items():
                    records.append(
                        (
                            str(o_id),
                            o_data.get("status", ""),
                            o_data.get("last_updated", last_updated),
                            json.dumps(o_data, ensure_ascii=False),
                        )
                    )
                if records:
                    with self.sql_engine.connect() as conn:
                        raw_conn = conn.connection
                        cursor = raw_conn.cursor()
                        cursor.execute(f"TRUNCATE TABLE {self.WRITE_TABLE}")
                        cursor.executemany(
                            f"INSERT INTO {self.WRITE_TABLE} (order_id, status, last_updated, data) VALUES (?, ?, ?, ?)",
                            records,
                        )
                        raw_conn.commit()
                        cursor.close()
            except Exception as e:
                import traceback

                print(f"⚠️ Error saving to SQL: {e}")
                traceback.print_exc()

        # Fallback / sync to JSON
        try:
            data = {"orders": self.orders, "last_updated": last_updated}
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"⚠️ Error saving to JSON: {e}")
            return False

    def import_from_sap(
        self, sap_order: Dict[str, Any], imported_by: str = "system"
    ) -> Dict[str, Any]:
        """Import an order from SAP data without modifying SAP."""
        order_id = str(sap_order.get("DocNum", sap_order.get("order_id", "")))

        if not order_id:
            raise ValueError("Order must have a DocNum or order_id")

        existing_status = None
        existing_history = []
        existing_imported_at = datetime.datetime.now().isoformat()
        existing_last_updated = datetime.datetime.now().isoformat()

        if order_id in self.orders:
            existing_status = self.orders[order_id].get("status")
            existing_history = self.orders[order_id].get("status_history", [])
            existing_imported_at = self.orders[order_id].get(
                "imported_at", existing_imported_at
            )
            existing_last_updated = self.orders[order_id].get(
                "last_updated", existing_last_updated
            )

        order_record = {
            "order_id": order_id,
            "customer_code": sap_order.get("CardCode", ""),
            "customer_name": sap_order.get("CardName", ""),
            "order_date": sap_order.get("DocDate", ""),
            "delivery_date": sap_order.get("DocDueDate", ""),
            "total": sap_order.get("DocTotal", 0),
            "currency": sap_order.get("DocCurrency", "MXN"),
            "comments": sap_order.get("Comments", ""),
            "items": sap_order.get("items", []),
            "sap_status": sap_order.get("sap_status", "Abierto"),
            "status": existing_status or OrderStatus.PENDING.value,
            "status_history": existing_history,
            "imported_at": existing_imported_at,
            "last_updated": existing_last_updated,
            "updated_by": (
                imported_by
                if not existing_status
                else self.orders.get(order_id, {}).get("updated_by", "system")
            ),
            "created_by": (
                imported_by
                if not existing_status
                else self.orders.get(order_id, {}).get("created_by", "system")
            ),
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
        self._save_database()

        return order_record

    def bulk_import_from_sap(self, sap_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import multiple orders from SAP at once."""
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

                order_data = {
                    "DocNum": sap_order["header"]["order_number"],
                    "CardCode": sap_order["header"].get("customer_code", ""),
                    "CardName": sap_order["header"].get("customer_name", ""),
                    "DocDate": sap_order["header"].get("order_date", ""),
                    "DocDueDate": sap_order["header"].get("delivery_date", ""),
                    "DocTotal": sap_order["header"].get("total_value", 0),
                    "DocCurrency": sap_order["header"].get("currency", "MXN"),
                    "sap_status": sap_order["header"].get("sap_status", "Abierto"),
                    "items": sap_order.get("items", []),
                    "updated_by": "system_sync",
                }

                self.import_from_sap(order_data)

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

        return stats

    def update_status(
        self, order_id: str, new_status: str, user: str, notes: str = ""
    ) -> bool:
        """Update the status of an order."""
        order_id = str(order_id)

        if order_id not in self.orders:
            print(f"⚠️ Order {order_id} not found")
            return False

        old_status = self.orders[order_id]["status"]

        self.orders[order_id]["status"] = new_status
        self.orders[order_id]["last_updated"] = datetime.datetime.now().isoformat()
        self.orders[order_id]["updated_by"] = user

        self.orders[order_id]["status_history"].append(
            {
                "status": new_status,
                "previous_status": old_status,
                "timestamp": datetime.datetime.now().isoformat(),
                "user": user,
                "notes": notes,
            }
        )

        return self._save_database()

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get a single order by ID."""
        return self.orders.get(str(order_id))

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders sorted by last updated."""
        orders_list = list(self.orders.values())
        orders_list.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return orders_list

    def get_orders_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get orders filtered by status."""
        return [o for o in self.orders.values() if o.get("status") == status]

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """Get orders that are not shipped or cancelled."""
        inactive_statuses = [
            OrderStatus.SHIPPED.value,
            OrderStatus.CANCELLED.value,
        ]
        active = [
            o for o in self.orders.values() if o.get("status") not in inactive_statuses
        ]
        active.sort(key=lambda x: x.get("order_date", ""), reverse=True)
        return active

    def get_order_count_by_status(self) -> Dict[str, int]:
        """Get count of orders grouped by status."""
        counts = {}
        for status in OrderStatus:
            counts[status.value] = len(self.get_orders_by_status(status.value))
        return counts

    def reconcile_statuses(self) -> int:
        """Fix orders where sap_status and local status are out of sync."""
        fixed = 0
        now_iso = datetime.datetime.now().isoformat()

        for order_id, order in self.orders.items():
            sap_status = order.get("sap_status", "")
            local_status = order.get("status", "")

            new_status = None
            if sap_status == "Cerrado" and local_status not in [
                OrderStatus.INVOICING.value,
                OrderStatus.READY.value,
                OrderStatus.SHIPPED.value,
            ]:
                new_status = OrderStatus.READY.value
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
                fixed += 1

        if fixed > 0:
            self._save_database()

        return fixed

    def delete_order(self, order_id: str) -> bool:
        """Delete an order from the local database."""
        order_id = str(order_id)
        if order_id in self.orders:
            del self.orders[order_id]
            return self._save_database()
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

