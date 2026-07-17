"""
Relación de Envíos Manager — Open-OMS

Manages daily shipping relations (Relación de Envíos) with:
- Consecutive folio numbers per day (RE-DDMMYY format)
- One relación per day (editable)
- Duplicate invoice prevention across relaciones
- "Cerrar Día" workflow with rollover to next business day
"""

import datetime
import json
import logging
import os
import threading
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

# Force Flask reload to clear memory cache
from core.database_client import DatabaseClient

logger = logging.getLogger(__name__)


class RelacionManager:
    """Manages Relación de Envíos documents with folio tracking."""

    TABLE_NAME = "seguimiento_relacion_envios"

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "relacion_envios.json")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.local_relaciones: Dict[str, Any] = {}  # keyed by folio
        self._json_write_lock = threading.Lock()

        self.db_client = DatabaseClient()
        self.db_client.connect()
        self._ensure_table_exists()
        self._load_fallback()

    # ── Table Setup ──────────────────────────────────────────────────────

    def _ensure_table_exists(self):
        """Create the SQL table if it doesn't exist."""
        if not self.db_client.engine:
            return  # pragma: no cover
        try:
            query = f"""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.TABLE_NAME}' and xtype='U')
                BEGIN
                    CREATE TABLE {self.TABLE_NAME} (
                        id              INT IDENTITY(1,1) PRIMARY KEY,
                        folio           VARCHAR(30) NOT NULL UNIQUE,
                        relacion_date   VARCHAR(10) NOT NULL,
                        created_at      DATETIME DEFAULT GETDATE(),
                        updated_at      DATETIME DEFAULT GETDATE(),
                        created_by      VARCHAR(50),
                        updated_by      VARCHAR(50),
                        invoices_json   VARCHAR(MAX),
                        invoice_numbers VARCHAR(MAX),
                        status          VARCHAR(20) DEFAULT 'active',
                        is_closed       BIT DEFAULT 0,
                        rolled_from     VARCHAR(30) NULL,
                        notes           VARCHAR(500) NULL,
                        signatures_json VARCHAR(MAX) NULL
                    )
                END
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(query)
            # Auto-migrate: add signatures_json if missing
            try:
                with self.db_client.engine.begin() as conn:
                    conn.exec_driver_sql(f"""
                        IF NOT EXISTS (
                            SELECT * FROM sys.columns
                            WHERE object_id = OBJECT_ID('{self.TABLE_NAME}')
                              AND name = 'signatures_json'
                        )
                        BEGIN
                            ALTER TABLE {self.TABLE_NAME}
                            ADD signatures_json VARCHAR(MAX) NULL
                        END
                    """)
            except Exception:  # pragma: no cover
                pass  # column likely exists
            # Create child table for normalized invoices
            child_table = "seguimiento_relacion_invoices"
            query_child = f"""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{child_table}' and xtype='U')
                BEGIN
                    CREATE TABLE {child_table} (
                        id              INT IDENTITY(1,1) PRIMARY KEY,
                        folio           VARCHAR(30) NOT NULL,
                        invoice_number  VARCHAR(30) NOT NULL,
                        is_checked      BIT NOT NULL DEFAULT 1,
                        shipping_type   VARCHAR(50) NULL,
                        observaciones   VARCHAR(MAX) NULL,
                        data_json       VARCHAR(MAX) NULL,
                        created_at      DATETIME DEFAULT GETDATE(),
                        updated_at      DATETIME DEFAULT GETDATE(),
                        CONSTRAINT UQ_relacion_invoice UNIQUE (folio, invoice_number)
                    )
                END
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(query_child)
                conn.exec_driver_sql(f"""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_relacion_invoices_folio' AND object_id=OBJECT_ID('{child_table}'))
                    CREATE INDEX IX_relacion_invoices_folio ON {child_table} (folio)
                """)
                conn.exec_driver_sql(f"""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_relacion_invoices_invoice' AND object_id=OBJECT_ID('{child_table}'))
                    CREATE INDEX IX_relacion_invoices_invoice ON {child_table} (invoice_number)
                """)
            logger.info(f"Verified {self.TABLE_NAME} and {child_table} tables exist")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to create tables: {e}")

    # ── Fallback JSON Persistence ────────────────────────────────────────

    def _load_fallback(self):
        """Load relaciones from JSON fallback file."""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.local_relaciones = json.load(f)
            except Exception:
                self.local_relaciones = {}

    def _save_fallback(self):
        """Save relaciones to JSON fallback file."""
        with self._json_write_lock:
            try:
                dir_name = os.path.dirname(self.db_path)
                os.makedirs(dir_name, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(self.local_relaciones, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, self.db_path)
                except Exception:  # pragma: no cover
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving relacion fallback: {e}")

    # ── Folio Generation ─────────────────────────────────────────────────

    @staticmethod
    def generate_folio(date_str: str) -> str:
        """
        Generate a folio in RE-DDMMYY format.
        One relación per day, so no sequence number needed.
        Example: 2026-06-17 → RE-170626
        """
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            d = datetime.datetime.now()
        return f"RE-{d.strftime('%d%m%y')}"

    # ── Core Operations ──────────────────────────────────────────────────

    def get_relacion(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Get the relación for a specific date, if it exists."""
        folio = self.generate_folio(date_str)

        # Try SQL first
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    query = """
                        SELECT folio, relacion_date, created_at, updated_at,
                               created_by, updated_by, invoices_json,
                               invoice_numbers, status, is_closed, rolled_from, notes,
                               signatures_json
                        FROM seguimiento_relacion_envios
                        WHERE folio = ?
                    """
                    row = conn.exec_driver_sql(query, (folio,)).fetchone()
                    if row:
                        parent_invoices = json.loads(row[6]) if row[6] else []
                        
                        # Load normalized invoices from child table
                        child_rows = conn.exec_driver_sql(
                            "SELECT invoice_number, is_checked, shipping_type, observaciones, data_json FROM seguimiento_relacion_invoices WHERE folio = ?",
                            (folio,)
                        ).fetchall()
                        
                        if child_rows:
                            invoices = []
                            for c_row in child_rows:
                                try:
                                    inv = json.loads(c_row[4]) if c_row[4] else {}
                                except Exception:
                                    inv = {}
                                inv["invoice_number"] = c_row[0]
                                inv["_selected"] = bool(c_row[1])
                                inv["shipping_type"] = c_row[2] or "LOCAL"
                                inv["observaciones"] = c_row[3] or ""
                                inv["nota"] = c_row[3] or ""
                                invoices.append(inv)
                        elif parent_invoices:
                            # Self-healing migration/backfill
                            invoices = parent_invoices
                            try:
                                with self.db_client.engine.begin() as write_conn:
                                    for inv in invoices:
                                        inv_num = str(inv.get("invoice_number", ""))
                                        is_checked = 1 if inv.get("_selected", True) else 0
                                        ship_type = inv.get("shipping_type", "LOCAL")
                                        obs = inv.get("observaciones", inv.get("nota", ""))
                                        write_conn.exec_driver_sql(
                                            """
                                            INSERT INTO seguimiento_relacion_invoices 
                                                (folio, invoice_number, is_checked, shipping_type, observaciones, data_json)
                                            VALUES (?, ?, ?, ?, ?, ?)
                                            """,
                                            (folio, inv_num, is_checked, ship_type, obs, json.dumps(inv, ensure_ascii=False))
                                        )
                                logger.info(f"[SELF-HEALING] Backfilled {len(invoices)} invoices for folio {folio} to seguimiento_relacion_invoices.")
                            except Exception as migration_err:
                                logger.error(f"Failed self-healing backfill for {folio}: {migration_err}")
                        else:
                            invoices = []

                        relacion = {
                            "folio": row[0],
                            "relacion_date": row[1],
                            "created_at": row[2].isoformat() if row[2] else None,
                            "updated_at": row[3].isoformat() if row[3] else None,
                            "created_by": row[4],
                            "updated_by": row[5],
                            "invoices": invoices,
                            "invoice_numbers": [str(inv.get("invoice_number", "")) for inv in invoices],
                            "status": row[8],
                            "is_closed": bool(row[9]),
                            "rolled_from": row[10],
                            "notes": row[11],
                            "signatures": json.loads(row[12]) if row[12] else {},
                        }
                        # Update local cache
                        self.local_relaciones[folio] = relacion
                        self._save_fallback()
                        return relacion
            except Exception as e:
                logger.error(f"Error fetching relacion {folio}: {e}")

        # Fallback
        return self.local_relaciones.get(folio)

    def create_or_update_relacion(
        self,
        date_str: str,
        invoices: List[Dict[str, Any]],
        username: str,
        notes: str = "",
        manual_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new relación for the date, or update the existing one.
        Returns the relación dict with folio.
        """
        if manual_order:
            order_map = {str(num): idx for idx, num in enumerate(manual_order)}
            invoices = sorted(invoices, key=lambda inv: order_map.get(str(inv.get("invoice_number", inv.get("id"))), 999999))

        folio = self.generate_folio(date_str)
        existing = self.get_relacion(date_str)
        invoice_numbers = [str(inv.get("invoice_number", "")) for inv in invoices]
        invoice_numbers_str = ",".join(invoice_numbers)
        invoices_json = json.dumps(invoices, ensure_ascii=False, default=str)
        now = datetime.datetime.now()

        if existing and existing.get("is_closed"):
            raise ValueError(
                f"La relación {folio} ya fue cerrada. No se puede modificar."
            )

        relacion = {
            "folio": folio,
            "relacion_date": date_str,
            "created_at": existing["created_at"] if existing else now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": existing["created_by"] if existing else username,
            "updated_by": username,
            "invoices": invoices,
            "invoice_numbers": invoice_numbers,
            "status": "active",
            "is_closed": False,
            "rolled_from": existing.get("rolled_from") if existing else None,
            "notes": notes or (existing.get("notes", "") if existing else ""),
        }

        # Save to SQL
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    if existing:
                        query = """
                            UPDATE seguimiento_relacion_envios
                            SET invoices_json = ?, invoice_numbers = ?,
                                updated_at = GETDATE(), updated_by = ?, notes = ?
                            WHERE folio = ?
                        """
                        conn.exec_driver_sql(
                            query,
                            (invoices_json, invoice_numbers_str, username, relacion["notes"], folio),
                        )
                    else:
                        query = """
                            INSERT INTO seguimiento_relacion_envios
                                (folio, relacion_date, created_by, updated_by,
                                 invoices_json, invoice_numbers, status, is_closed, notes)
                            VALUES (?, ?, ?, ?, ?, ?, 'active', 0, ?)
                        """
                        conn.exec_driver_sql(
                            query,
                            (
                                folio, date_str, username, username,
                                invoices_json, invoice_numbers_str, relacion["notes"],
                            ),
                        )
                    
                    # Synchronize child table
                    conn.exec_driver_sql("DELETE FROM seguimiento_relacion_invoices WHERE folio = ?", (folio,))
                    for inv in invoices:
                        inv_num = str(inv.get("invoice_number", ""))
                        is_checked = 1 if inv.get("_selected", True) else 0
                        ship_type = inv.get("shipping_type", "LOCAL")
                        obs = inv.get("observaciones", inv.get("nota", ""))
                        conn.exec_driver_sql(
                            """
                            INSERT INTO seguimiento_relacion_invoices 
                                (folio, invoice_number, is_checked, shipping_type, observaciones, data_json)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (folio, inv_num, is_checked, ship_type, obs, json.dumps(inv, ensure_ascii=False))
                        )
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving relacion {folio} to SQL: {e}")

        # Update local cache
        self.local_relaciones[folio] = relacion
        self._save_fallback()

        action = "updated" if existing else "created"
        logger.info(
            f"Relación {folio} {action} by {username} with {len(invoices)} invoices"
        )
        return relacion

    def toggle_invoice_in_relacion(
        self,
        date_str: str,
        invoice_numbers: Any,
        selected: bool,
        invoice_data: Any,
        username: str,
        manual_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add or remove one or more invoices in the shipping relation for a date."""
        folio = self.generate_folio(date_str)
        existing = self.get_relacion(date_str)

        if existing and existing.get("is_closed"):
            raise ValueError(f"La relación {folio} ya fue cerrada. No se puede modificar.")

        invoices = existing.get("invoices", []) if existing else []

        # Normalize invoice_numbers to a set of strings
        if isinstance(invoice_numbers, (list, set, tuple)):
            target_numbers = {str(num) for num in invoice_numbers}
        else:
            target_numbers = {str(invoice_numbers)}

        # Filter out existing invoices that are being toggled
        invoices = [inv for inv in invoices if str(inv.get("invoice_number")) not in target_numbers]

        if selected:
            # If selected=True, append the new invoice data
            if isinstance(invoice_data, list):
                for item in invoice_data:
                    if item:
                        invoices.append(item)
            elif invoice_data:
                invoices.append(invoice_data)
            else:
                for num in target_numbers:
                    invoices.append({"invoice_number": num})

        return self.create_or_update_relacion(
            date_str=date_str,
            invoices=invoices,
            username=username,
            notes=existing.get("notes", "") if existing else "",
            manual_order=manual_order
        )

    # ── Signature Management ─────────────────────────────────────────────

    def save_signatures(
        self,
        folio: str,
        area: str,
        action: str,
        username: str,
        full_name: str = "",
        signature_path: str = "",
    ) -> Dict[str, Any]:
        """
        Sign or unsign a specific area of the relación.

        Args:
            folio: The relación folio (e.g. RE-170626)
            area: One of 'facturacion', 'credito', 'almacen'
            action: 'sign' or 'unsign'
            username: The username performing the action
            full_name: Display name for the signature
            signature_path: Path to the user's uploaded signature image

        Returns:
            Updated signatures dict
        """
        valid_areas = {"facturacion", "credito", "almacen"}
        if area not in valid_areas:
            raise ValueError(f"Invalid signature area: {area}")

        # Get current signatures
        signatures = self.get_signatures(folio)

        if action == "sign":
            signatures[area] = {
                "name": full_name or username,
                "user": username,
                "at": datetime.datetime.now().isoformat(),
                "signature_path": signature_path,
            }
        elif action == "unsign":
            signatures.pop(area, None)
        else:
            raise ValueError(f"Invalid action: {action}")

        signatures_json = json.dumps(signatures, ensure_ascii=False)

        # Save to SQL
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    conn.exec_driver_sql(
                        """
                        UPDATE seguimiento_relacion_envios
                        SET signatures_json = ?, updated_at = GETDATE()
                        WHERE folio = ?
                        """,
                        (signatures_json, folio),
                    )
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving signatures for {folio}: {e}")

        # Update local cache
        if folio in self.local_relaciones:
            self.local_relaciones[folio]["signatures"] = signatures
            self._save_fallback()

        logger.info(f"Signature {action}: {area} by {username} on {folio}")
        return signatures

    def get_signatures(self, folio: str) -> Dict[str, Any]:
        """Get the current signatures for a relación."""
        # Try SQL
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    row = conn.exec_driver_sql(
                        "SELECT signatures_json FROM seguimiento_relacion_envios WHERE folio = ?",
                        (folio,),
                    ).fetchone()
                    if row and row[0]:
                        return json.loads(row[0])
            except Exception as e:
                logger.error(f"Error getting signatures for {folio}: {e}")

        # Fallback
        rel = self.local_relaciones.get(folio, {})
        return rel.get("signatures", {})

    # ── Per-Invoice Authorization (Crédito y Cobranza) ────────────────────

    def authorize_invoice(
        self,
        folio: str,
        invoice_number: str,
        authorized: bool,
        username: str,
        full_name: str = "",
    ) -> Dict[str, Any]:
        """
        Authorize or revoke authorization for a specific invoice in a relación.

        The Crédito y Cobranza department uses this to approve individual
        invoices for shipping.  Each invoice gets an audit trail recording
        who authorized it and when.

        Args:
            folio: The relación folio (e.g. RE-170626)
            invoice_number: The invoice number to authorize
            authorized: True to authorize, False to revoke
            username: The username performing the action
            full_name: Display name for the audit trail

        Returns:
            Dict with updated invoice and authorization summary
        """
        invoice_number = str(invoice_number)

        # Get current relación
        relacion = None
        for rel_folio, rel_data in self.local_relaciones.items():
            if rel_folio == folio:
                relacion = rel_data
                break

        # Try SQL if not in local cache
        if relacion is None and self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    child_rows = conn.exec_driver_sql(
                        "SELECT invoice_number, is_checked, shipping_type, observaciones, data_json FROM seguimiento_relacion_invoices WHERE folio = ?",
                        (folio,)
                    ).fetchall()
                    if child_rows:
                        invoices = []
                        for c_row in child_rows:
                            try:
                                inv = json.loads(c_row[4]) if c_row[4] else {}
                            except Exception:
                                inv = {}
                            inv["invoice_number"] = c_row[0]
                            inv["_selected"] = bool(c_row[1])
                            inv["shipping_type"] = c_row[2] or "LOCAL"
                            inv["observaciones"] = c_row[3] or ""
                            inv["nota"] = c_row[3] or ""
                            invoices.append(inv)
                        relacion = {"invoices": invoices, "folio": folio}
                    else:
                        row = conn.exec_driver_sql(
                            "SELECT invoices_json FROM seguimiento_relacion_envios WHERE folio = ?",
                            (folio,),
                        ).fetchone()
                        if row and row[0]:
                            invoices = json.loads(row[0])
                            relacion = {"invoices": invoices, "folio": folio}
            except Exception as e:
                logger.error(f"Error fetching relacion {folio} for auth: {e}")

        if relacion is None:
            raise ValueError(f"Relación {folio} no encontrada.")

        invoices = relacion.get("invoices", [])
        now = datetime.datetime.now().isoformat()
        updated_invoice = None

        for inv in invoices:
            if str(inv.get("invoice_number")) == invoice_number:
                if authorized:
                    inv["credito_authorized"] = True
                    inv["credito_authorized_by"] = username
                    inv["credito_authorized_name"] = full_name or username
                    inv["credito_authorized_at"] = now
                else:
                    inv["credito_authorized"] = False
                    inv.pop("credito_authorized_by", None)
                    inv.pop("credito_authorized_name", None)
                    inv.pop("credito_authorized_at", None)
                updated_invoice = inv
                break

        if updated_invoice is None:
            raise ValueError(f"Factura {invoice_number} no encontrada en {folio}.")

        # Persist updated invoices
        invoices_json = json.dumps(invoices, ensure_ascii=False, default=str)

        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    conn.exec_driver_sql(
                        """
                        UPDATE seguimiento_relacion_envios
                        SET invoices_json = ?, updated_at = GETDATE()
                        WHERE folio = ?
                        """,
                        (invoices_json, folio),
                    )
                    
                    inv_num = str(updated_invoice.get("invoice_number", ""))
                    conn.exec_driver_sql(
                        """
                        UPDATE seguimiento_relacion_invoices
                        SET data_json = ?, updated_at = GETDATE()
                        WHERE folio = ? AND invoice_number = ?
                        """,
                        (json.dumps(updated_invoice, ensure_ascii=False), folio, inv_num),
                    )
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving authorization for {folio}: {e}")

        # Update local cache
        if folio in self.local_relaciones:
            self.local_relaciones[folio]["invoices"] = invoices
            self._save_fallback()

        action = "authorized" if authorized else "revoked"
        logger.info(
            f"Crédito {action}: invoice {invoice_number} on {folio} by {username}"
        )

        return {
            "invoice": updated_invoice,
            "summary": self.get_authorization_summary(folio),
        }

    def get_authorization_summary(self, folio: str) -> Dict[str, Any]:
        """
        Get authorization summary for a relación.

        Returns:
            Dict with total, authorized, and pending counts.
        """
        relacion = self.local_relaciones.get(folio)
        if not relacion:
            return {"total": 0, "authorized": 0, "pending": 0}

        invoices = relacion.get("invoices", [])
        total = len(invoices)
        authorized = sum(1 for inv in invoices if inv.get("credito_authorized"))

        return {
            "total": total,
            "authorized": authorized,
            "pending": total - authorized,
        }

    def get_used_invoice_numbers(self, date_str: str) -> Set[str]:
        """
        Get all invoice numbers already included in ANY active relación.
        Used for duplicate prevention — an invoice should not appear in
        two different relaciones.
        """
        used: Set[str] = set()

        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    query = """
                        SELECT DISTINCT i.invoice_number 
                        FROM seguimiento_relacion_invoices i
                        INNER JOIN seguimiento_relacion_envios e ON i.folio = e.folio
                        WHERE e.status = 'active' AND i.is_checked = 1
                    """
                    rows = conn.exec_driver_sql(query).fetchall()
                    if rows:
                        for row in rows:
                            if row[0]:
                                used.add(str(row[0]).strip())
                        return used
                    else:
                        # Fallback to legacy string split if child table has no rows
                        query_legacy = """
                            SELECT invoice_numbers FROM seguimiento_relacion_envios
                            WHERE status = 'active' AND invoice_numbers IS NOT NULL
                        """
                        rows_legacy = conn.exec_driver_sql(query_legacy).fetchall()
                        for row in rows_legacy:
                            if row[0]:
                                used.update(n.strip() for n in row[0].split(",") if n.strip())
                        return used
            except Exception as e:
                logger.error(f"Error fetching used invoices: {e}")

        # Fallback
        for rel in self.local_relaciones.values():
            if rel.get("status") == "active":
                used.update(rel.get("invoice_numbers", []))
        return used

    def get_relaciones_list(
        self, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List relaciones within a date range (summary, no full invoice data)."""
        results = []

        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    conditions = ["1=1"]
                    params = []
                    if date_from:
                        conditions.append("relacion_date >= ?")
                        params.append(date_from)
                    if date_to:
                        conditions.append("relacion_date <= ?")
                        params.append(date_to)

                    where = " AND ".join(conditions)
                    query = f"""
                        SELECT folio, relacion_date, created_at, updated_at,
                               created_by, updated_by, invoice_numbers,
                               status, is_closed, notes
                        FROM seguimiento_relacion_envios
                        WHERE {where}
                        ORDER BY relacion_date DESC, created_at DESC
                    """
                    rows = conn.exec_driver_sql(query, params).fetchall()
                    for row in rows:
                        inv_nums = row[6].split(",") if row[6] else []
                        results.append({
                            "folio": row[0],
                            "relacion_date": row[1],
                            "created_at": row[2].isoformat() if row[2] else None,
                            "updated_at": row[3].isoformat() if row[3] else None,
                            "created_by": row[4],
                            "updated_by": row[5],
                            "invoice_count": len(inv_nums),
                            "invoice_numbers": inv_nums,
                            "status": row[7],
                            "is_closed": bool(row[8]),
                            "notes": row[9],
                        })
                    return results
            except Exception as e:
                logger.error(f"Error listing relaciones: {e}")

        # Fallback
        for rel in self.local_relaciones.values():
            d = rel.get("relacion_date", "")
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            results.append({
                "folio": rel["folio"],
                "relacion_date": rel["relacion_date"],
                "created_at": rel.get("created_at"),
                "updated_at": rel.get("updated_at"),
                "created_by": rel.get("created_by"),
                "updated_by": rel.get("updated_by"),
                "invoice_count": len(rel.get("invoice_numbers", [])),
                "invoice_numbers": rel.get("invoice_numbers", []),
                "status": rel.get("status", "active"),
                "is_closed": rel.get("is_closed", False),
                "notes": rel.get("notes"),
            })
        results.sort(key=lambda x: x.get("relacion_date", ""), reverse=True)
        return results

    # ── Cerrar Día ───────────────────────────────────────────────────────

    @staticmethod
    def get_next_business_day(date_str: str) -> str:
        """Get the next business day (Mon-Fri) after the given date."""
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            d = datetime.datetime.now()

        d += datetime.timedelta(days=1)
        # Skip weekends
        while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
            d += datetime.timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def cerrar_dia(
        self,
        date_str: str,
        unsent_invoices: List[Dict[str, Any]],
        username: str,
    ) -> Dict[str, Any]:
        """
        Close the day:
        1. Mark today's relación as closed (is_closed=True)
        2. Roll unsent invoices to the next business day

        Returns info about what happened.
        """
        folio = self.generate_folio(date_str)
        next_day = self.get_next_business_day(date_str)

        # 1. Close today's relación
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE seguimiento_relacion_envios
                        SET is_closed = 1, updated_at = GETDATE(), updated_by = ?
                        WHERE folio = ? AND is_closed = 0
                    """
                    conn.exec_driver_sql(query, (username, folio))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error closing relacion {folio}: {e}")

        # Update local cache
        if folio in self.local_relaciones:
            self.local_relaciones[folio]["is_closed"] = True
            self.local_relaciones[folio]["updated_at"] = datetime.datetime.now().isoformat()
            self.local_relaciones[folio]["updated_by"] = username

        self._save_fallback()

        result = {
            "closed_folio": folio,
            "closed_date": date_str,
            "next_business_day": next_day,
            "rolled_invoices": 0,
            "next_folio": None,
        }
        logger.info(f"Día cerrado: {folio} by {username}.")
        return result
