"""
SAP HANA Connector — Order Tracking Module
Trimmed version: only order-related methods.

Connects to SAP HANA via hdbcli to retrieve:
- Sales Orders (ORDR/RDR1)
- Order Status
- Invoice linkage (OINV/INV1)
"""

import logging
import os
import threading
import time

import pandas as pd
from hdbcli import dbapi

logger = logging.getLogger(__name__)


class SAPHanaConnector:
    """
    SAP HANA connector for order tracking.
    Uses hdbcli (native Python driver) for connectivity.
    """

    DEFAULT_HOST = os.environ.get("SAP_HANA_HOST", "")
    DEFAULT_PORT = int(os.environ.get("SAP_HANA_PORT", "30015"))
    DEFAULT_SCHEMA = os.environ.get("SAP_HANA_SCHEMA", "SBO_QUIMICABOSS")
    DEFAULT_USER = os.environ.get("SAP_HANA_USER", "")
    DEFAULT_PASS = os.environ.get("SAP_HANA_PASSWORD", "")

    TABLES = {
        "sales_orders": "ORDR",
        "sales_order_lines": "RDR1",
        "customers": "OCRD",
        "invoices": "OINV",
        "invoice_lines": "INV1",
        "delivery_notes": "ODLN",
        "delivery_lines": "DLN1",
    }

    # Circuit-breaker settings
    CB_FAILURE_THRESHOLD = 3   # consecutive failures before opening circuit
    CB_COOLDOWN_SECONDS = 60   # seconds to wait before retrying after circuit opens

    def __init__(self, host=None, port=None, username=None, password=None, schema=None):
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self.username = username or self.DEFAULT_USER
        self.password = password or self.DEFAULT_PASS
        self.schema = schema or self.DEFAULT_SCHEMA
        self._local = threading.local()
        self._local.connection = None
        self._local.connected = False

        # Circuit-breaker state (shared across threads)
        self._cb_lock = threading.Lock()
        self._cb_consecutive_failures = 0
        self._cb_last_failure_time = 0.0

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
                connectTimeout=5000,  # type: ignore[call-arg]
            )
            self._local.connected = True
            logger.info("[OK] SAP HANA connection established successfully")
            return True
        except dbapi.Error as e:
            logger.error(f"[ERROR] SAP HANA connection failed: {e}")
            self._local.connected = False
            self._local.connection = None
            raise
        except Exception as e:
            logger.error(
                f"[ERROR] Fatal error establishing SAP connection: {str(e)}", exc_info=True
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

    def _ping_connection(self) -> bool:
        """Returns True if the current thread's connection is alive."""
        conn = getattr(self._local, "connection", None)
        if not conn:  # pragma: no cover
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM DUMMY")
            cursor.close()
            return True
        except Exception:  # pragma: no cover
            return False  # pragma: no cover

    def _ensure_connected(self):
        connected = getattr(self._local, "connected", False)
        conn = getattr(self._local, "connection", None)

        if connected and conn:
            # Use a fast ping instead of trusting internal driver state blindly
            if not self._ping_connection():  # pragma: no cover
                connected = False

        if not connected:
            # Circuit-breaker: fail fast if SAP has been unreachable
            with self._cb_lock:
                if self._cb_consecutive_failures >= self.CB_FAILURE_THRESHOLD:  # pragma: no cover
                    elapsed = time.time() - self._cb_last_failure_time
                    if elapsed < self.CB_COOLDOWN_SECONDS:
                        raise ConnectionError(
                            f"SAP circuit-breaker OPEN — {self._cb_consecutive_failures} "
                            f"consecutive failures, retrying in "
                            f"{int(self.CB_COOLDOWN_SECONDS - elapsed)}s"
                        )
                    # Cooldown expired — allow one retry (half-open)
                    logger.info("SAP circuit-breaker half-open — attempting reconnect")

            try:
                self.connect()
                # Success — reset circuit-breaker
                with self._cb_lock:
                    self._cb_consecutive_failures = 0
            except Exception:
                with self._cb_lock:
                    self._cb_consecutive_failures += 1
                    self._cb_last_failure_time = time.time()
                    logger.warning(
                        f"SAP circuit-breaker: failure #{self._cb_consecutive_failures} "
                        f"(threshold={self.CB_FAILURE_THRESHOLD})"
                    )
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
              AND "CardCode" != 'CL1662'
            ORDER BY "DocDate" DESC
            LIMIT {limit}
        """

        return pd.read_sql(query, getattr(self._local, "connection", None))

    def get_recent_orders(self, limit=10, only_open=False):
        """Get recent sales orders with full details.

        Uses a batch approach (3 queries total) instead of N+1 individual
        get_order_details() calls to avoid 22-32 second response times.
        """
        self._ensure_connected()

        slp_codes = "('12', '23', '6', '13', '14', '11', '15', '5', '8', '17', '3', '19', '7', '4', '10', '-1')"
        where_clause = f'WHERE T0."SlpCode" IN {slp_codes} AND T0."CardCode" != \'CL1662\''

        if only_open:
            where_clause += ' AND T0."DocStatus" = \'O\' AND (T0."CANCELED" = \'N\' OR T0."CANCELED" IS NULL)'

        # ── Query 1: Fetch all headers in one shot ───────────────────────
        header_query = f"""
            SELECT
                T0."DocNum"     AS order_number,
                T0."CardCode"   AS customer_code,
                T0."CardName"   AS customer_name,
                T0."DocDate"    AS order_date,
                T0."DocTime"    AS order_time,
                T0."DocDueDate" AS delivery_date,
                T0."DocTotal"   AS total_value,
                T0."DocCur"     AS currency,
                T0."DocEntry"   AS doc_entry,
                T0."DocStatus"  AS doc_status,
                T0."CANCELED"   AS canceled,
                T0."Printed"    AS printed,
                T3."SlpName"    AS creator_name
            FROM {self._get_table_name("sales_orders")} T0
            LEFT JOIN {self.schema}."OSLP" T3 ON T0."SlpCode" = T3."SlpCode"
            {where_clause}
            ORDER BY T0."DocNum" DESC
            LIMIT {limit}
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")
        cursor = conn.cursor()
        cursor.execute(header_query)
        header_rows = cursor.fetchall()

        if not header_rows:
            cursor.close()
            return []

        # Build header dicts and collect doc_entries for batch lookups
        headers_by_entry = {}  # doc_entry -> header dict
        doc_entries = []

        for row in header_rows:
            doc_entry = int(row[8])
            doc_status = row[9] if len(row) > 9 else "O"
            canceled = row[10] if len(row) > 10 else "N"

            if canceled == "Y":  # pragma: no cover
                sap_status = "Cancelado"
            elif doc_status == "C":
                sap_status = "Cerrado"
            else:
                sap_status = "Abierto"

            order_date = str(row[3])
            order_time = row[4]
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

            header = {
                "order_number": int(row[0]),
                "customer_code": row[1],
                "customer_name": row[2],
                "order_date": order_datetime,
                "delivery_date": str(row[5]),
                "total_value": float(row[6]) if row[6] else 0,
                "currency": row[7],
                "doc_entry": doc_entry,
                "sap_status": sap_status,
                "doc_status": doc_status,
                "canceled": canceled,
                "factura_number": None,  # filled in query 2
                "delivery_number": None,  # filled in query 2.5
                "creator_name": row[12] if len(row) > 12 and row[12] else "SAP System",
                "updater_name": row[12] if len(row) > 12 and row[12] else "SAP System",
            }
            headers_by_entry[doc_entry] = header
            doc_entries.append(doc_entry)

        # ── Query 2: Batch fetch invoice numbers ─────────────────────────
        if doc_entries:
            placeholders = ",".join(["?" for _ in doc_entries])
            invoice_query = f"""
                SELECT DISTINCT T1."BaseEntry", T0."DocNum"
                FROM {self._get_table_name("invoices")} T0
                INNER JOIN {self._get_table_name("invoice_lines")} T1
                    ON T0."DocEntry" = T1."DocEntry"
                WHERE T1."BaseType" = 17
                  AND T1."BaseEntry" IN ({placeholders})
            """
            try:
                cursor.execute(invoice_query, doc_entries)
                for inv_row in cursor.fetchall():
                    base_entry = int(inv_row[0])
                    if base_entry in headers_by_entry:
                        headers_by_entry[base_entry]["factura_number"] = str(int(inv_row[1]))
            except Exception as e:  # pragma: no cover
                logger.warning(f"Batch invoice lookup failed: {e}")  # pragma: no cover

        # ── Query 2.5: Batch fetch delivery note numbers ─────────────────
        if doc_entries:
            placeholders = ",".join(["?" for _ in doc_entries])
            delivery_num_query = f"""
                SELECT DISTINCT T1."BaseEntry", T0."DocNum"
                FROM {self._get_table_name("delivery_notes")} T0
                INNER JOIN {self._get_table_name("delivery_lines")} T1
                    ON T0."DocEntry" = T1."DocEntry"
                WHERE T1."BaseType" = 17
                  AND T1."BaseEntry" IN ({placeholders})
            """
            try:
                cursor.execute(delivery_num_query, doc_entries)
                for del_row in cursor.fetchall():
                    base_entry = int(del_row[0])
                    if base_entry in headers_by_entry:
                        headers_by_entry[base_entry]["delivery_number"] = str(int(del_row[1]))
            except Exception as e:  # pragma: no cover
                logger.warning(f"Batch delivery note lookup failed: {e}")  # pragma: no cover

        # ── Query 3: Batch fetch line items ──────────────────────────────
        items_by_entry = {de: [] for de in doc_entries}
        if doc_entries:
            placeholders = ",".join(["?" for _ in doc_entries])
            items_query = f"""
                SELECT
                    T1."DocEntry"       AS doc_entry,
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
                WHERE T1."DocEntry" IN ({placeholders})
                ORDER BY T1."DocEntry", T1."LineNum"
            """
            cursor.execute(items_query, doc_entries)

            def _safe_float(v):
                try:
                    return float(v) if v is not None else 0.0
                except (ValueError, TypeError):  # pragma: no cover
                    return 0.0  # pragma: no cover

            for row in cursor.fetchall():
                entry = int(row[0])
                items_by_entry.setdefault(entry, []).append({
                    "line_number": int(row[1]),
                    "item_code": row[2],
                    "description": row[3],
                    "quantity": _safe_float(row[4]),
                    "unit": row[5],
                    "unit_price": _safe_float(row[6]),
                    "line_total": _safe_float(row[7]),
                    "warehouse": row[8],
                    "u_tara": _safe_float(row[9]),
                    "u_num_etiqueta": int(_safe_float(row[10])) if row[10] else 0,
                    "u_presentacion": str(row[11]).strip() if row[11] else "",
                    "u_kilos_pre": _safe_float(row[12]),
                })

        cursor.close()

        # ── Assemble results ─────────────────────────────────────────────
        all_orders = []
        for doc_entry in doc_entries:
            header = headers_by_entry[doc_entry]
            items = items_by_entry.get(doc_entry, [])
            all_orders.append({"header": header, "items": items})

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

        if not header_row or header_row[1] == "CL1662":
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

        # Get Delivery note number (Nota de Entrega)
        delivery_query = f"""
            SELECT DISTINCT T0."DocNum"
            FROM {self._get_table_name("delivery_notes")} T0
            INNER JOIN {self._get_table_name("delivery_lines")} T1 ON T0."DocEntry" = T1."DocEntry"
            WHERE T1."BaseType" = 17 AND T1."BaseEntry" = ?
        """
        try:
            cursor.execute(delivery_query, [int(header_row[8])])
            del_row = cursor.fetchone()
            delivery_number = str(int(del_row[0])) if del_row else None
        except Exception as e:  # pragma: no cover
            logger.warning(  # pragma: no cover
                f"Could not fetch delivery note number for order {order_number}: {e}"
            )
            delivery_number = None  # pragma: no cover

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
            "delivery_number": delivery_number,
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

    # =========================================================================
    # DELIVERY NOTE & INVOICE BATCH LOOKUPS (for status automation)
    # =========================================================================

    def get_delivery_notes_batch(self, doc_entries):  # pragma: no cover
        """Batch-check which sales orders have delivery notes (ODLN/DLN1).

        A delivery note means the warehouse has finished picking the order.
        Returns a dict: {doc_entry: delivery_info_dict, ...}

        Args:
            doc_entries: list of ORDR.DocEntry integers to check.

        Returns:
            Dict mapping doc_entry → {delivery_num, delivery_date, delivery_status}
        """
        if not doc_entries:
            return {}

        self._ensure_connected()
        results = {}
        chunk_size = 500

        for i in range(0, len(doc_entries), chunk_size):
            chunk = doc_entries[i: i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])

            query = f"""
                SELECT DISTINCT
                    L1."BaseEntry"  AS order_doc_entry,
                    D0."DocNum"     AS delivery_num,
                    D0."DocDate"    AS delivery_date,
                    D0."DocStatus"  AS delivery_status
                FROM {self._get_table_name("delivery_notes")} D0
                INNER JOIN {self._get_table_name("delivery_lines")} L1
                    ON D0."DocEntry" = L1."DocEntry"
                WHERE L1."BaseType" = 17
                  AND L1."BaseEntry" IN ({placeholders})
                ORDER BY D0."DocNum" DESC
            """
            try:
                conn = getattr(self._local, "connection", None)
                if conn is None:
                    raise ConnectionError("No active connection")
                cursor = conn.cursor()
                cursor.execute(query, chunk)

                for row in cursor.fetchall():
                    entry = int(row[0])
                    if entry not in results:  # keep only first (latest) delivery
                        results[entry] = {
                            "delivery_num": int(row[1]),
                            "delivery_date": str(row[2]),
                            "delivery_status": row[3] or "O",
                        }
                cursor.close()
            except Exception as e:
                logger.warning(f"Batch delivery note lookup failed for chunk {i}: {e}")

        return results

    def get_invoices_for_orders_batch(self, doc_entries):  # pragma: no cover
        """Batch-check which sales orders have invoices (OINV/INV1).

        Returns a dict: {doc_entry: invoice_num, ...}

        Args:
            doc_entries: list of ORDR.DocEntry integers to check.

        Returns:
            Dict mapping doc_entry → invoice_num (int)
        """
        if not doc_entries:
            return {}

        self._ensure_connected()
        results = {}
        chunk_size = 500

        for i in range(0, len(doc_entries), chunk_size):
            chunk = doc_entries[i: i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])

            query = f"""
                SELECT DISTINCT
                    I1."BaseEntry"  AS order_doc_entry,
                    I0."DocNum"     AS invoice_num
                FROM {self._get_table_name("invoices")} I0
                INNER JOIN {self._get_table_name("invoice_lines")} I1
                    ON I0."DocEntry" = I1."DocEntry"
                WHERE I1."BaseType" = 17
                  AND I1."BaseEntry" IN ({placeholders})
                UNION
                SELECT DISTINCT
                    D1."BaseEntry"  AS order_doc_entry,
                    I0."DocNum"     AS invoice_num
                FROM {self._get_table_name("invoices")} I0
                INNER JOIN {self._get_table_name("invoice_lines")} I1
                    ON I0."DocEntry" = I1."DocEntry"
                INNER JOIN {self._get_table_name("delivery_lines")} D1
                    ON I1."BaseType" = 15 AND I1."BaseEntry" = D1."DocEntry"
                WHERE D1."BaseType" = 17
                  AND D1."BaseEntry" IN ({placeholders})
            """
            try:
                conn = getattr(self._local, "connection", None)
                if conn is None:
                    raise ConnectionError("No active connection")
                cursor = conn.cursor()
                cursor.execute(query, chunk + chunk)

                for row in cursor.fetchall():
                    entry = int(row[0])
                    if entry not in results:
                        results[entry] = int(row[1])
                cursor.close()
            except Exception as e:
                logger.warning(f"Batch invoice lookup failed for chunk {i}: {e}")

        return results

    def get_recent_deliveries_and_invoices_audit(self, limit=100):  # pragma: no cover
        """Fetch the most recent delivery notes and invoices from SAP for reaction audit.

        Returns:
            Tuple of (deliveries_list, invoices_list)
        """
        self._ensure_connected()
        deliveries = []
        invoices = []

        delivery_query = f"""
            SELECT DISTINCT
                L1."BaseEntry"  AS order_doc_entry,
                D0."DocNum"     AS delivery_num,
                D0."DocDate"    AS delivery_date,
                D0."DocTime"    AS delivery_time
            FROM {self._get_table_name("delivery_notes")} D0
            INNER JOIN {self._get_table_name("delivery_lines")} L1 ON D0."DocEntry" = L1."DocEntry"
            WHERE L1."BaseType" = 17
            ORDER BY D0."DocEntry" DESC
            LIMIT ?
        """

        invoice_query = f"""
            SELECT * FROM (
                SELECT DISTINCT
                    I1."BaseEntry"  AS order_doc_entry,
                    I0."DocNum"     AS invoice_num,
                    I0."DocDate"    AS invoice_date,
                    I0."DocTime"    AS invoice_time,
                    I0."DocEntry"   AS doc_entry
                FROM {self._get_table_name("invoices")} I0
                INNER JOIN {self._get_table_name("invoice_lines")} I1 ON I0."DocEntry" = I1."DocEntry"
                WHERE I1."BaseType" = 17
                UNION
                SELECT DISTINCT
                    D1."BaseEntry"  AS order_doc_entry,
                    I0."DocNum"     AS invoice_num,
                    I0."DocDate"    AS invoice_date,
                    I0."DocTime"    AS invoice_time,
                    I0."DocEntry"   AS doc_entry
                FROM {self._get_table_name("invoices")} I0
                INNER JOIN {self._get_table_name("invoice_lines")} I1 ON I0."DocEntry" = I1."DocEntry"
                INNER JOIN {self._get_table_name("delivery_lines")} D1 ON I1."BaseType" = 15 AND I1."BaseEntry" = D1."DocEntry"
                WHERE D1."BaseType" = 17
            ) T
            ORDER BY T.doc_entry DESC
            LIMIT ?
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")

        cursor = conn.cursor()

        # Fetch deliveries
        try:
            cursor.execute(delivery_query, [limit])
            for row in cursor.fetchall():
                doc_date = row[2]
                doc_time = row[3]
                dt_str = self._parse_sap_datetime_helper(doc_date, doc_time)
                deliveries.append({
                    "order_doc_entry": int(row[0]),
                    "doc_num": str(row[1]),
                    "sap_date": dt_str,
                })
        except Exception as e:
            logger.error(f"Audit: failed to query delivery notes: {e}")

        # Fetch invoices
        try:
            cursor.execute(invoice_query, [limit])
            for row in cursor.fetchall():
                doc_date = row[2]
                doc_time = row[3]
                dt_str = self._parse_sap_datetime_helper(doc_date, doc_time)
                invoices.append({
                    "order_doc_entry": int(row[0]),
                    "doc_num": str(row[1]),
                    "sap_date": dt_str,
                })
        except Exception as e:
            logger.error(f"Audit: failed to query invoices: {e}")

        cursor.close()
        return deliveries, invoices

    def _parse_sap_datetime_helper(self, doc_date, doc_time):  # pragma: no cover
        if not doc_date:
            return None
        date_str = str(doc_date).split(" ")[0].split("T")[0]
        try:
            if doc_time and int(doc_time) > 0:
                time_val = str(int(doc_time)).zfill(4)
                hours = int(time_val[:2])
                minutes = int(time_val[2:4])
                return f"{date_str} {hours:02d}:{minutes:02d}:00"
            return f"{date_str} 00:00:00"
        except Exception:
            return f"{date_str} 00:00:00"

    # =========================================================================
    # INVOICE QUERIES
    # =========================================================================

    def get_todays_invoices(self, date_str=None, extra_invoice_numbers=None):
        """Fetch invoices for a given date (defaults to today), optionally including specific invoice numbers.

        Args:
            date_str: Optional date string in 'YYYY-MM-DD' format.
                      If None, uses the current date on the SAP server.
            extra_invoice_numbers: Optional list of specific invoice numbers to include regardless of date.

        Returns:
            List of invoice dicts with header information.
        """
        self._ensure_connected()
        if date_str:
            base_filter = f"T0.\"DocDate\" = '{date_str}'"
        else:
            base_filter = 'T0."DocDate" = CURRENT_DATE'
        base_filter += """
              AND (T1."TrnspName" != 'VENTA MOSTRADOR' OR T1."TrnspName" IS NULL)
              AND T0."CardCode" != 'CL1662'
        """

        if extra_invoice_numbers:
            try:  # pragma: no cover
                nums = ",".join(str(int(n)) for n in extra_invoice_numbers if n)
                if nums:
                    final_filter = f"""({base_filter}) 
                    OR T0."DocNum" IN ({nums})
                    OR EXISTS (
                        SELECT 1 FROM {self._get_table_name("sales_orders")} R0
                        INNER JOIN {self._get_table_name("invoice_lines")} L2
                            ON L2."BaseType" = 17 AND L2."BaseEntry" = R0."DocEntry"
                        WHERE L2."DocEntry" = T0."DocEntry" AND R0."DocNum" IN ({nums})
                    )
                    OR EXISTS (
                        SELECT 1 FROM {self._get_table_name("sales_orders")} R0
                        INNER JOIN {self._get_table_name("delivery_lines")} D1
                            ON D1."BaseType" = 17 AND D1."BaseEntry" = R0."DocEntry"
                        INNER JOIN {self._get_table_name("invoice_lines")} L3
                            ON L3."BaseType" = 15 AND L3."BaseEntry" = D1."DocEntry"
                        WHERE L3."DocEntry" = T0."DocEntry" AND R0."DocNum" IN ({nums})
                    )"""
                else:
                    final_filter = base_filter
            except (ValueError, TypeError):  # pragma: no cover
                final_filter = base_filter
        else:
            final_filter = base_filter

        if date_str:
            sub_base = f"T0.\"DocDate\" = '{date_str}'"
        else:
            sub_base = 'T0."DocDate" = CURRENT_DATE'
        sub_base += ' AND T0."CardCode" != \'CL1662\''

        subquery_filter = sub_base
        if extra_invoice_numbers:
            try:  # pragma: no cover
                nums = ",".join(str(int(n)) for n in extra_invoice_numbers if n)
                if nums:
                    subquery_filter = f"({sub_base}) OR T0.\"DocNum\" IN ({nums})"
            except (ValueError, TypeError):  # pragma: no cover
                pass

        query = f"""
            SELECT
                T0."DocNum"    AS invoice_number,
                T0."DocEntry"  AS doc_entry,
                T0."CardCode"  AS customer_code,
                T0."CardName"  AS customer_name,
                T0."DocDate"   AS invoice_date,
                T0."DocTotal"  AS total,
                T0."DocCur"    AS currency,
                T0."DocStatus" AS doc_status,
                T0."CANCELED"  AS canceled,
                T0."Comments"  AS comments,
                T3."SlpName"   AS seller_name,
                T0."PaidToDate" AS paid_to_date,
                T1."TrnspName" AS shipping_type,
                T2."PymntGroup" AS payment_terms,
                WH.warehouse   AS warehouse,
                SO.order_number AS order_number,
                SO.order_date   AS order_date
            FROM {self._get_table_name("invoices")} T0
            LEFT JOIN {self.schema}."OSLP" T3 ON T0."SlpCode" = T3."SlpCode"
            LEFT JOIN {self.schema}."OSHP" T1 ON T0."TrnspCode" = T1."TrnspCode"
            LEFT JOIN {self.schema}."OCTG" T2 ON T0."GroupNum" = T2."GroupNum"
            LEFT JOIN (
                SELECT 
                    L1."DocEntry" AS InvoiceDocEntry,
                    MAX(L1."WhsCode") AS warehouse
                FROM {self._get_table_name("invoice_lines")} L1
                INNER JOIN {self._get_table_name("invoices")} T0
                    ON T0."DocEntry" = L1."DocEntry"
                WHERE {subquery_filter}
                GROUP BY L1."DocEntry"
            ) WH ON T0."DocEntry" = WH.InvoiceDocEntry
            LEFT JOIN (
                SELECT 
                    InvoiceDocEntry,
                    MAX(OrderNum) AS order_number,
                    MAX(OrderDate) AS order_date
                FROM (
                    SELECT 
                        L2."DocEntry" AS InvoiceDocEntry,
                        R0."DocNum" AS OrderNum,
                        R0."DocDate" AS OrderDate
                    FROM {self._get_table_name("sales_orders")} R0
                    INNER JOIN {self._get_table_name("invoice_lines")} L2
                        ON L2."BaseType" = 17 AND L2."BaseEntry" = R0."DocEntry"
                    INNER JOIN {self._get_table_name("invoices")} T0
                        ON T0."DocEntry" = L2."DocEntry"
                    WHERE {subquery_filter}
                    
                    UNION ALL
                    
                    SELECT 
                        L3."DocEntry" AS InvoiceDocEntry,
                        R0."DocNum" AS OrderNum,
                        R0."DocDate" AS OrderDate
                    FROM {self._get_table_name("sales_orders")} R0
                    INNER JOIN {self._get_table_name("delivery_lines")} D1
                        ON D1."BaseType" = 17 AND D1."BaseEntry" = R0."DocEntry"
                    INNER JOIN {self._get_table_name("invoice_lines")} L3
                        ON L3."BaseType" = 15 AND L3."BaseEntry" = D1."DocEntry"
                    INNER JOIN {self._get_table_name("invoices")} T0
                        ON T0."DocEntry" = L3."DocEntry"
                    WHERE {subquery_filter}
                )
                GROUP BY InvoiceDocEntry
            ) SO ON T0."DocEntry" = SO.InvoiceDocEntry
            WHERE {final_filter}
            ORDER BY T0."DocNum" DESC
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")

        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()

        invoices = []
        for row in rows:
            canceled = row[8] or "N"
            doc_status = row[7] or "O"

            if canceled == "Y":
                status = "Cancelada"
            elif doc_status == "C":
                status = "Cerrada"
            else:
                status = "Abierta"

            shipping_type = row[12] or "LOCAL"
            if shipping_type.strip().upper() in ["ENVIO LOCAL", "ENVÍO LOCAL"]:
                shipping_type = "LOCAL"  # pragma: no cover

            invoices.append({
                "invoice_number": int(row[0]),
                "doc_entry": int(row[1]),
                "customer_code": row[2] or "",
                "customer_name": row[3] or "",
                "invoice_date": str(row[4]),
                "total": float(row[5]) if row[5] else 0.0,
                "currency": row[6] or "MXN",
                "status": status,
                "doc_status": doc_status,
                "canceled": canceled,
                "comments": row[9] or "",
                "seller_name": row[10] or "SAP System",
                "paid_to_date": float(row[11]) if row[11] else 0.0,
                "shipping_type": shipping_type,
                "payment_terms": row[13] or "CONTADO",
                "warehouse": row[14] or "",
                "order_number": int(row[15]) if row[15] else None,
                "order_date": str(row[16]) if row[16] else "",
            })

        return invoices

    def get_invoice_lines(self, doc_entry):
        """Fetch line items for a specific invoice.

        Args:
            doc_entry: The DocEntry of the invoice.

        Returns:
            List of line item dicts.
        """
        self._ensure_connected()

        query = f"""
            SELECT
                T1."LineNum"    AS line_number,
                T1."ItemCode"   AS item_code,
                T1."Dscription" AS description,
                T1."Quantity"   AS quantity,
                T1."unitMsr"    AS unit,
                T1."Price"      AS unit_price,
                T1."LineTotal"  AS line_total,
                T1."WhsCode"    AS warehouse
            FROM {self._get_table_name("invoice_lines")} T1
            WHERE T1."DocEntry" = ?
            ORDER BY T1."LineNum"
        """

        conn = getattr(self._local, "connection", None)
        if conn is None:
            raise ConnectionError("No active connection")

        cursor = conn.cursor()
        cursor.execute(query, [doc_entry])
        rows = cursor.fetchall()
        cursor.close()

        items = []
        for row in rows:
            def _safe_float(v):
                try:
                    return float(v) if v is not None else 0.0
                except (ValueError, TypeError):  # pragma: no cover
                    return 0.0  # pragma: no cover

            items.append({
                "line_number": int(row[0]),
                "item_code": row[1] or "",
                "description": row[2] or "",
                "quantity": _safe_float(row[3]),
                "unit": row[4] or "",
                "unit_price": _safe_float(row[5]),
                "line_total": _safe_float(row[6]),
                "warehouse": row[7] or "",
            })

        return items
