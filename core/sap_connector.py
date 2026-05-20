"""
SAP HANA Connector — Order Tracking Module
Trimmed version: only order-related methods.

Connects to SAP HANA via hdbcli to retrieve:
- Sales Orders (ORDR/RDR1)
- Order Status
- Invoice linkage (OINV/INV1)
"""

import logging
import threading

import pandas as pd
from hdbcli import dbapi

logger = logging.getLogger(__name__)


class SAPHanaConnector:
    """
    SAP HANA connector for order tracking.
    Uses hdbcli (native Python driver) for connectivity.
    """

    DEFAULT_HOST = "20.0.1.9"
    DEFAULT_PORT = 30015
    DEFAULT_SCHEMA = "SBO_QUIMICABOSS"
    DEFAULT_USER = "SYSTEM"
    DEFAULT_PASS = "Qui20Mi25B#"

    TABLES = {
        "sales_orders": "ORDR",
        "sales_order_lines": "RDR1",
        "customers": "OCRD",
        "invoices": "OINV",
        "invoice_lines": "INV1",
        "delivery_notes": "ODLN",
        "delivery_lines": "DLN1",
    }

    def __init__(self, host=None, port=None, username=None, password=None, schema=None):
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self.username = username or self.DEFAULT_USER
        self.password = password or self.DEFAULT_PASS
        self.schema = schema or self.DEFAULT_SCHEMA
        self._local = threading.local()
        self._local.connection = None
        self._local.connected = False

    def connect(self, username=None, password=None):
        user = username or self.username
        pwd = password or self.password

        if not user or not pwd:
            raise ValueError(
                "Username and password are required for SAP HANA connection"
            )

        try:
            logger.info(f"Connecting to SAP HANA at {self.host}:{self.port}...")
            self._local.connection = dbapi.connect(
                address=self.host,
                port=self.port,
                user=user,
                password=pwd,
                timeout=10,  # type: ignore[call-arg]
                connectTimeout=10000,  # type: ignore[call-arg]
            )
            self._local.connected = True
            logger.info("✅ SAP HANA connection established successfully")
            return True
        except dbapi.Error as e:
            logger.error(f"❌ SAP HANA connection failed: {e}")
            self._local.connected = False
            self._local.connection = None
            raise
        except Exception as e:
            logger.error(
                f"❌ Fatal error establishing SAP connection: {str(e)}", exc_info=True
            )
            self._local.connection = None
            self._local.connected = False
            return False

    @property
    def connected(self):
        return getattr(self._local, "connected", False)

    @property
    def connection(self):
        return getattr(self._local, "connection", None)

    def disconnect(self):
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            self._local.connected = False
            logger.info("SAP HANA connection closed")

    def _get_table_name(self, table_key):
        table = self.TABLES.get(table_key, table_key)
        if self.schema:
            return f'"{self.schema}"."{table}"'
        return f'"{table}"'

    def _ensure_connected(self):
        if not getattr(self._local, "connected", False):
            try:
                self.connect()
            except Exception:
                raise ConnectionError(
                    "Not connected to SAP HANA and auto-connection failed"
                )

    # =========================================================================
    # SALES ORDER QUERIES
    # =========================================================================

    def get_sales_orders(self, days_back=30, limit=500):
        """Retrieve recent sales orders from SAP Business One."""
        self._ensure_connected()

        query = f"""
            SELECT
                "DocNum" as order_number,
                "CardCode" as customer_code,
                "CardName" as customer_name,
                "DocDate" as order_date,
                "DocDueDate" as delivery_date,
                "DocTotal" as total_value,
                "DocCur" as currency,
                "DocEntry" as doc_entry
            FROM {self._get_table_name("sales_orders")}
            WHERE "DocDate" >= ADD_DAYS(CURRENT_DATE, -{days_back})
              AND "SlpCode" IN ('12', '23', '6', '13', '14', '11', '15', '5', '8', '17', '3', '19', '7', '4', '10', '-1')
            ORDER BY "DocDate" DESC
            LIMIT {limit}
        """

        return pd.read_sql(query, getattr(self._local, "connection", None))

    def get_recent_orders(self, limit=10, only_open=False):
        """Get recent sales orders with full details."""
        self._ensure_connected()

        slp_codes = "('12', '23', '6', '13', '14', '11', '15', '5', '8', '17', '3', '19', '7', '4', '10', '-1')"
        where_clause = f'WHERE T0."SlpCode" IN {slp_codes}'

        if only_open:
            where_clause += ' AND T0."DocStatus" = \'O\' AND (T0."CANCELED" = \'N\' OR T0."CANCELED" IS NULL)'

        query = f"""
            SELECT
                T0."DocNum" AS order_number,
                T0."DocEntry" AS doc_entry
            FROM {self._get_table_name("sales_orders")} T0
            {where_clause}
            ORDER BY T0."DocNum" DESC
            LIMIT {limit}
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")
        cursor = conn.cursor()
        cursor.execute(query)
        order_numbers = cursor.fetchall()
        cursor.close()

        all_orders = []
        for row in order_numbers:
            order_num = int(row[0])
            order_details = self.get_order_details(order_num)
            if order_details:
                all_orders.append(order_details)

        return all_orders

    def get_all_open_orders(self):
        """Get all open sales orders."""
        return self.get_recent_orders(limit=100, only_open=True)

    def get_order_details(self, order_number):
        """Get complete order details with line items."""
        self._ensure_connected()

        header_query = f"""
            SELECT
                T0."DocNum" AS order_number,
                T0."CardCode" AS customer_code,
                T0."CardName" AS customer_name,
                T0."DocDate" AS order_date,
                T0."DocTime" AS order_time,
                T0."DocDueDate" AS delivery_date,
                T0."DocTotal" AS total_value,
                T0."DocCur" AS currency,
                T0."DocEntry" AS doc_entry,
                T0."DocStatus" AS doc_status,
                T0."CANCELED" AS canceled,
                T0."Printed" AS printed,
                T3."SlpName" AS creator_name,
                T3."SlpName" AS updater_name
            FROM {self._get_table_name("sales_orders")} T0
            LEFT JOIN {self.schema}."OSLP" T3 ON T0."SlpCode" = T3."SlpCode"
            WHERE T0."DocNum" = ?
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")
        cursor = conn.cursor()
        cursor.execute(header_query, [order_number])
        header_row = cursor.fetchone()

        if not header_row:
            cursor.close()
            return None

        doc_status = header_row[9] if len(header_row) > 9 else "O"
        canceled = header_row[10] if len(header_row) > 10 else "N"

        if canceled == "Y":
            sap_status = "Cancelado"
        elif doc_status == "C":
            sap_status = "Cerrado"
        else:
            sap_status = "Abierto"

        order_date = str(header_row[3])
        order_time = header_row[4]

        try:
            if order_time and order_time > 0:
                time_str = str(int(order_time)).zfill(4)
                hours = int(time_str[:2])
                minutes = int(time_str[2:4])
                order_datetime = f"{order_date} {hours:02d}:{minutes:02d}:00"
            else:
                order_datetime = f"{order_date}"
        except Exception:  # pragma: no cover
            order_datetime = f"{order_date}"  # pragma: no cover

        # Get Invoice number (Factura)
        invoice_query = f"""
            SELECT DISTINCT T0."DocNum"
            FROM {self._get_table_name("invoices")} T0
            INNER JOIN {self._get_table_name("invoice_lines")} T1 ON T0."DocEntry" = T1."DocEntry"
            WHERE (T1."BaseType" = 17 AND T1."BaseEntry" = ?)
               OR (T1."BaseType" = 15 AND T1."BaseEntry" IN (
                   SELECT "DocEntry" FROM {self._get_table_name("delivery_lines")} WHERE "BaseType" = 17 AND "BaseEntry" = ?
               ))
        """
        try:
            cursor.execute(invoice_query, [int(header_row[8]), int(header_row[8])])
            inv_row = cursor.fetchone()
            factura_number = str(int(inv_row[0])) if inv_row else None
        except Exception as e:  # pragma: no cover
            logger.warning(  # pragma: no cover
                f"Could not fetch invoice number for order {order_number}: {e}"
            )
            factura_number = None  # pragma: no cover

        header = {
            "order_number": int(header_row[0]),
            "customer_code": header_row[1],
            "customer_name": header_row[2],
            "order_date": order_datetime,
            "delivery_date": str(header_row[5]),
            "total_value": float(header_row[6]) if header_row[6] else 0,
            "currency": header_row[7],
            "doc_entry": int(header_row[8]),
            "sap_status": sap_status,
            "doc_status": doc_status,
            "canceled": canceled,
            "factura_number": factura_number,
            "creator_name": header_row[12]
            if len(header_row) > 12 and header_row[12]
            else "SAP System",
            "updater_name": header_row[13]
            if len(header_row) > 13 and header_row[13]
            else "SAP System",
        }

        # Get line items
        items_query = f"""
            SELECT
                T1."LineNum"        AS line_number,
                T1."ItemCode"       AS item_code,
                T1."Dscription"     AS description,
                T1."Quantity"       AS quantity,
                T1."unitMsr"        AS unit,
                T1."Price"          AS unit_price,
                T1."LineTotal"      AS line_total,
                T1."WhsCode"        AS warehouse,
                T1."U_Tara"         AS u_tara,
                T1."U_NumEtiqueta"  AS u_num_etiqueta,
                T1."U_Presentacion" AS u_presentacion,
                T1."U_KilosPre"     AS u_kilos_pre
            FROM {self._get_table_name("sales_order_lines")} T1
            WHERE T1."DocEntry" = ?
            ORDER BY T1."LineNum"
        """

        cursor.execute(items_query, [header["doc_entry"]])
        items = []
        for row in cursor.fetchall():

            def _safe_float(v):
                try:
                    return float(v) if v is not None else 0.0
                except (ValueError, TypeError):  # pragma: no cover
                    return 0.0  # pragma: no cover

            items.append(
                {
                    "line_number": int(row[0]),
                    "item_code": row[1],
                    "description": row[2],
                    "quantity": _safe_float(row[3]),
                    "unit": row[4],
                    "unit_price": _safe_float(row[5]),
                    "line_total": _safe_float(row[6]),
                    "warehouse": row[7],
                    "u_tara": _safe_float(row[8]),
                    "u_num_etiqueta": int(_safe_float(row[9])) if row[9] else 0,
                    "u_presentacion": str(row[10]).strip() if row[10] else "",
                    "u_kilos_pre": _safe_float(row[11]),
                }
            )

        cursor.close()

        return {"header": header, "items": items}

    def get_orders_status_batch(self, order_numbers):
        """Fetch SAP status for multiple orders in a single query."""
        if not order_numbers:
            return {}

        self._ensure_connected()

        results = {}
        chunk_size = 500

        for i in range(0, len(order_numbers), chunk_size):
            chunk = order_numbers[i : i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])

            query = f"""
                SELECT
                    T0."DocNum",
                    T0."DocStatus",
                    T0."CANCELED",
                    T0."CardName",
                    T3."SlpName" AS updater_name
                FROM {self._get_table_name("sales_orders")} T0
                LEFT JOIN {self.schema}."OSLP" T3 ON T0."SlpCode" = T3."SlpCode"
                WHERE T0."DocNum" IN ({placeholders})
            """

            try:
                conn = getattr(self._local, "connection", None)
                if conn is None:
                    raise ConnectionError("No active connection")
                cursor = conn.cursor()
                cursor.execute(query, chunk)

                for row in cursor.fetchall():
                    doc_num = int(row[0])
                    doc_status = row[1] or "O"
                    canceled = row[2] or "N"
                    customer_name = row[3] or ""
                    updater_name = row[4] or "SAP System"

                    if canceled == "Y":
                        sap_status = "Cancelado"
                    elif doc_status == "C":
                        sap_status = "Cerrado"
                    else:
                        sap_status = "Abierto"

                    results[doc_num] = {
                        "sap_status": sap_status,
                        "doc_status": doc_status,
                        "canceled": canceled,
                        "updater_name": updater_name,
                        "customer_name": customer_name,
                    }

                cursor.close()
            except Exception as e:
                logger.error(f"Batch status query failed for chunk {i}: {e}")
                try:
                    self.connect()
                except Exception:  # pragma: no cover
                    pass  # pragma: no cover

        return results
