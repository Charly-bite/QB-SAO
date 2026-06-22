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
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

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
            logger.info(f"Verified {self.TABLE_NAME} table exists")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to create {self.TABLE_NAME}: {e}")

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
                    row = conn.exec_driver_sql(query, [folio]).fetchone()
                    if row:
                        relacion = {
                            "folio": row[0],
                            "relacion_date": row[1],
                            "created_at": row[2].isoformat() if row[2] else None,
                            "updated_at": row[3].isoformat() if row[3] else None,
                            "created_by": row[4],
                            "updated_by": row[5],
                            "invoices": json.loads(row[6]) if row[6] else [],
                            "invoice_numbers": row[7].split(",") if row[7] else [],
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
    ) -> Dict[str, Any]:
        """
        Create a new relación for the date, or update the existing one.
        Returns the relación dict with folio.
        """
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
                            [invoices_json, invoice_numbers_str, username, relacion["notes"], folio],
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
                            [
                                folio, date_str, username, username,
                                invoices_json, invoice_numbers_str, relacion["notes"],
                            ],
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

    # ── Signature Management ─────────────────────────────────────────────

    def save_signatures(
        self,
        folio: str,
        area: str,
        action: str,
        username: str,
        full_name: str = "",
    ) -> Dict[str, Any]:
        """
        Sign or unsign a specific area of the relación.

        Args:
            folio: The relación folio (e.g. RE-170626)
            area: One of 'facturacion', 'credito', 'almacen'
            action: 'sign' or 'unsign'
            username: The username performing the action
            full_name: Display name for the signature

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
                        [signatures_json, folio],
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
                        [folio],
                    ).fetchone()
                    if row and row[0]:
                        return json.loads(row[0])
            except Exception as e:
                logger.error(f"Error getting signatures for {folio}: {e}")

        # Fallback
        rel = self.local_relaciones.get(folio, {})
        return rel.get("signatures", {})


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
                        SELECT invoice_numbers FROM seguimiento_relacion_envios
                        WHERE status = 'active' AND invoice_numbers IS NOT NULL
                    """
                    rows = conn.exec_driver_sql(query).fetchall()
                    for row in rows:
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
                    conn.exec_driver_sql(query, [username, folio])
            except Exception as e:  # pragma: no cover
                logger.error(f"Error closing relacion {folio}: {e}")

        # Update local cache
        if folio in self.local_relaciones:
            self.local_relaciones[folio]["is_closed"] = True
            self.local_relaciones[folio]["updated_at"] = datetime.datetime.now().isoformat()
            self.local_relaciones[folio]["updated_by"] = username

        # 2. Roll unsent invoices to next business day
        rolled_count = 0
        if unsent_invoices:
            next_folio = self.generate_folio(next_day)
            existing_next = self.get_relacion(next_day)

            if existing_next:
                # Merge with existing — add only new invoices
                existing_nums = set(existing_next.get("invoice_numbers", []))
                new_invoices = existing_next.get("invoices", [])[:]
                for inv in unsent_invoices:
                    inv_num = str(inv.get("invoice_number", ""))
                    if inv_num not in existing_nums:
                        new_invoices.append(inv)
                        rolled_count += 1
                if rolled_count > 0:
                    self.create_or_update_relacion(
                        next_day, new_invoices, username,
                        notes=f"Incluye {rolled_count} facturas del {date_str}"
                    )
            else:
                # Create new relación for next day with rolled invoices
                rolled_count = len(unsent_invoices)
                rel = self.create_or_update_relacion(
                    next_day, unsent_invoices, username,
                    notes=f"Rollover de {rolled_count} facturas del {date_str}"
                )
                # Mark the rolled_from reference
                if self.db_client.engine:
                    try:
                        with self.db_client.engine.begin() as conn:
                            conn.exec_driver_sql(
                                "UPDATE seguimiento_relacion_envios SET rolled_from = ? WHERE folio = ?",
                                [folio, next_folio]
                            )
                    except Exception:  # pragma: no cover
                        pass

        self._save_fallback()

        result = {
            "closed_folio": folio,
            "closed_date": date_str,
            "next_business_day": next_day,
            "rolled_invoices": rolled_count,
            "next_folio": self.generate_folio(next_day) if rolled_count > 0 else None,
        }
        logger.info(
            f"Día cerrado: {folio} by {username}. "
            f"Rolled {rolled_count} invoices to {next_day}"
        )
        return result
