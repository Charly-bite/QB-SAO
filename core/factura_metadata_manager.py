import logging
import os
import json
import tempfile
from core.database_client import DatabaseClient

logger = logging.getLogger(__name__)

class FacturaMetadataManager:
    TABLE_NAME = "factura_metadata"

    def __init__(self, db_path=None):
        if db_path is None:
            # Store runtime data in project-root /data/, not inside the source /core/ dir
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "factura_metadata.json")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.local_metadata = {}
        self.local_daily_orders = {}
        self.local_daily_extras = {}

        self.db_client = DatabaseClient()
        self.db_client.connect()
        self._ensure_table_exists()
        self._load_fallback()

    def _ensure_table_exists(self):
        try:
            if not self.db_client.engine:
                return

            check_query = f"""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.TABLE_NAME}' and xtype='U')
                BEGIN
                    CREATE TABLE {self.TABLE_NAME} (
                        invoice_number INT PRIMARY KEY,
                        override_category VARCHAR(50) NULL,
                        color VARCHAR(20) NULL,
                        custom_customer_name VARCHAR(150) NULL
                    )
                END
                ELSE
                BEGIN
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'color')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD color VARCHAR(20) NULL;
                        ALTER TABLE {self.TABLE_NAME} ALTER COLUMN override_category VARCHAR(50) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'custom_customer_name')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD custom_customer_name VARCHAR(150) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'credito_authorized')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD credito_authorized BIT NULL;
                        ALTER TABLE {self.TABLE_NAME} ADD credito_authorized_by VARCHAR(50) NULL;
                        ALTER TABLE {self.TABLE_NAME} ADD credito_authorized_at VARCHAR(50) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'credito_revoked_from_relacion')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD credito_revoked_from_relacion BIT NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'credito_notes')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD credito_notes VARCHAR(MAX) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'sent_to_credito')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD sent_to_credito BIT NULL;
                    END
                END
                
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='factura_daily_order' and xtype='U')
                BEGIN
                    CREATE TABLE factura_daily_order (
                        order_date VARCHAR(20) PRIMARY KEY,
                        manual_order_json VARCHAR(MAX) NULL
                    )
                END

                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='factura_daily_extra' and xtype='U')
                BEGIN
                    CREATE TABLE factura_daily_extra (
                        order_date VARCHAR(20) PRIMARY KEY,
                        extra_invoices_json VARCHAR(MAX) NULL
                    )
                END
                
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_credito_autorizaciones' and xtype='U')
                BEGIN
                    CREATE TABLE seguimiento_credito_autorizaciones (
                        invoice_number                  INT PRIMARY KEY,
                        credito_authorized              BIT NOT NULL DEFAULT 0,
                        credito_authorized_by           VARCHAR(50) NULL,
                        credito_authorized_at           VARCHAR(50) NULL,
                        credito_revoked_from_relacion   BIT NOT NULL DEFAULT 0,
                        credito_notes                   VARCHAR(MAX) NULL,
                        sent_to_credito                 BIT NOT NULL DEFAULT 0,
                        created_at                      DATETIME DEFAULT GETDATE(),
                        updated_at                      DATETIME DEFAULT GETDATE()
                    )
                END
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(check_query)
            logger.info(f"Verified tables exist (including seguimiento_credito_autorizaciones)")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to verify/create tables: {e}")

    def _load_fallback(self):
        """Loads metadata from JSON file fallback"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.local_metadata = json.load(f)
            except Exception as e:
                self.local_metadata = {}
                
        daily_path = os.path.join(os.path.dirname(self.db_path), "factura_daily_order.json")
        if os.path.exists(daily_path):
            try:
                with open(daily_path, "r", encoding="utf-8") as f:
                    self.local_daily_orders = json.load(f)
            except Exception:  # pragma: no cover
                self.local_daily_orders = {}

        extra_path = os.path.join(os.path.dirname(self.db_path), "factura_daily_extra.json")
        if os.path.exists(extra_path):
            try:
                with open(extra_path, "r", encoding="utf-8") as f:
                    self.local_daily_extras = json.load(f)
            except Exception:  # pragma: no cover
                self.local_daily_extras = {}

    def _save_fallback(self):
        """Saves metadata to JSON file fallback"""
        try:
            dir_name = os.path.dirname(self.db_path)
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.local_metadata, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.db_path)
            except Exception:  # pragma: no cover
                # Always clean up the temp file so we never leave orphans on disk
                try:  # pragma: no cover
                    os.unlink(tmp_path)  # pragma: no cover
                except OSError:  # pragma: no cover
                    pass  # pragma: no cover
                raise  # pragma: no cover
        except Exception as e:  # pragma: no cover
            logger.error(f"Error saving JSON fallback: {e}")

    def _save_daily_fallback(self):
        try:
            daily_path = os.path.join(os.path.dirname(self.db_path), "factura_daily_order.json")
            dir_name = os.path.dirname(self.db_path)
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.local_daily_orders, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, daily_path)
            except Exception:  # pragma: no cover
                # Always clean up the temp file so we never leave orphans on disk
                try:  # pragma: no cover
                    os.unlink(tmp_path)  # pragma: no cover
                except OSError:  # pragma: no cover
                    pass  # pragma: no cover
                raise  # pragma: no cover
        except Exception as e:  # pragma: no cover
            logger.error(f"Error saving daily order JSON fallback: {e}")

    def _save_extra_fallback(self):
        try:
            extra_path = os.path.join(os.path.dirname(self.db_path), "factura_daily_extra.json")
            dir_name = os.path.dirname(self.db_path)
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.local_daily_extras, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, extra_path)
            except Exception:  # pragma: no cover
                # Always clean up the temp file so we never leave orphans on disk
                try:  # pragma: no cover
                    os.unlink(tmp_path)  # pragma: no cover
                except OSError:  # pragma: no cover
                    pass  # pragma: no cover
                raise  # pragma: no cover
        except Exception as e:  # pragma: no cover
            logger.error(f"Error saving daily extra JSON fallback: {e}")

    def get_overrides(self):
        """Returns (overrides_dict, colors_dict, custom_names_dict)"""
        overrides = {}
        colors = {}
        custom_names = {}
        # 1. Load from local fallback first
        for k, v in self.local_metadata.items():
            try:
                if isinstance(v, dict):
                    if v.get("category"): overrides[int(k)] = v.get("category")
                    if v.get("color"): colors[int(k)] = v.get("color")
                    if v.get("custom_customer_name"): custom_names[int(k)] = v.get("custom_customer_name")
                else:  # pragma: no cover
                    overrides[int(k)] = v
            except ValueError:  # pragma: no cover
                pass  # pragma: no cover
                
        # 2. Try to load from SQL Server and merge
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    result = conn.exec_driver_sql(f"SELECT invoice_number, override_category, color, custom_customer_name FROM {self.TABLE_NAME}").fetchall()
                    for row in result:  # pragma: no cover
                        inv, cat, col, cust_name = row[0], row[1], row[2], row[3]
                        if cat: overrides[inv] = cat
                        if col: colors[inv] = col
                        if cust_name: custom_names[inv] = cust_name
                        self.local_metadata[str(inv)] = {
                            "category": cat or "",
                            "color": col or "",
                            "custom_customer_name": cust_name or ""
                        }
                    self._save_fallback()
            except Exception as e:  # pragma: no cover
                logger.error(f"Error fetching factura metadata from SQL: {e}")
                
        return overrides, colors, custom_names

    def get_credito_authorizations(self):  # pragma: no cover
        auths = {}
        # 1. Load from local fallback
        for k, v in self.local_metadata.items():
            if isinstance(v, dict) and (v.get("credito_authorized") is not None or v.get("sent_to_credito") is not None):
                auths[int(k)] = {
                    "credito_authorized": v.get("credito_authorized"),
                    "credito_authorized_by": v.get("credito_authorized_by"),
                    "credito_authorized_at": v.get("credito_authorized_at"),
                    "credito_revoked_from_relacion": v.get("credito_revoked_from_relacion", False),
                    "credito_notes": v.get("credito_notes", ""),
                    "sent_to_credito": v.get("sent_to_credito", False)
                }
        
        # 2. Try SQL
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    # Query the new normalized table
                    result = conn.exec_driver_sql(
                        """
                        SELECT invoice_number, credito_authorized, credito_authorized_by, 
                               credito_authorized_at, credito_revoked_from_relacion, 
                               credito_notes, sent_to_credito 
                        FROM seguimiento_credito_autorizaciones
                        """
                    ).fetchall()
                    
                    if result:
                        for row in result:
                            inv = row[0]
                            auths[inv] = {
                                "credito_authorized": bool(row[1]) if row[1] is not None else False,
                                "credito_authorized_by": row[2],
                                "credito_authorized_at": row[3],
                                "credito_revoked_from_relacion": bool(row[4]) if len(row) > 4 and row[4] is not None else False,
                                "credito_notes": row[5] if len(row) > 5 and row[5] is not None else "",
                                "sent_to_credito": bool(row[6]) if len(row) > 6 and row[6] is not None else False
                            }
                            if str(inv) not in self.local_metadata or not isinstance(self.local_metadata[str(inv)], dict):
                                self.local_metadata[str(inv)] = {"category": "", "color": "", "custom_customer_name": ""}
                            self.local_metadata[str(inv)].update(auths[inv])
                        self._save_fallback()
                    else:
                        # Self-healing migration from legacy factura_metadata table
                        # Check if old table has any credit data
                        legacy_query = f"""
                            SELECT invoice_number, credito_authorized, credito_authorized_by, 
                                   credito_authorized_at, credito_revoked_from_relacion, 
                                   credito_notes, sent_to_credito 
                            FROM {self.TABLE_NAME} 
                            WHERE credito_authorized IS NOT NULL 
                               OR credito_revoked_from_relacion = 1 
                               OR credito_notes IS NOT NULL 
                               OR sent_to_credito = 1
                        """
                        legacy_rows = conn.exec_driver_sql(legacy_query).fetchall()
                        if legacy_rows:
                            try:
                                with self.db_client.engine.begin() as write_conn:
                                    for row in legacy_rows:
                                        inv = row[0]
                                        auth_val = 1 if row[1] else 0
                                        by = row[2]
                                        at = row[3]
                                        revoked = 1 if row[4] else 0
                                        notes = row[5] or ""
                                        sent = 1 if row[6] else 0
                                        
                                        write_conn.exec_driver_sql(
                                            """
                                            INSERT INTO seguimiento_credito_autorizaciones 
                                                (invoice_number, credito_authorized, credito_authorized_by, 
                                                 credito_authorized_at, credito_revoked_from_relacion, 
                                                 credito_notes, sent_to_credito)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                            """,
                                            (inv, auth_val, by, at, revoked, notes, sent)
                                        )
                                        
                                        # Also populate auths dict
                                        auths[inv] = {
                                            "credito_authorized": bool(row[1]) if row[1] is not None else False,
                                            "credito_authorized_by": row[2],
                                            "credito_authorized_at": row[3],
                                            "credito_revoked_from_relacion": bool(row[4]) if row[4] is not None else False,
                                            "credito_notes": row[5] if row[5] is not None else "",
                                            "sent_to_credito": bool(row[6]) if row[6] is not None else False
                                        }
                                        if str(inv) not in self.local_metadata or not isinstance(self.local_metadata[str(inv)], dict):
                                            self.local_metadata[str(inv)] = {"category": "", "color": "", "custom_customer_name": ""}
                                        self.local_metadata[str(inv)].update(auths[inv])
                                logger.info(f"[SELF-HEALING] Migrated {len(legacy_rows)} credit records to seguimiento_credito_autorizaciones.")
                                self._save_fallback()
                            except Exception as migration_err:
                                logger.error(f"Failed to migrate legacy credit auths: {migration_err}")
            except Exception as e:
                logger.error(f"Error fetching credito auths: {e}")
        return auths

    def save_credito_authorization(self, invoice_number: int, authorized: bool, by: str, at: str):  # pragma: no cover
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["credito_authorized"] = authorized
        self.local_metadata[inv_str]["credito_authorized_by"] = by
        self.local_metadata[inv_str]["credito_authorized_at"] = at
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE seguimiento_credito_autorizaciones 
                        SET credito_authorized = ?, credito_authorized_by = ?, credito_authorized_at = ?, updated_at = GETDATE()
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO seguimiento_credito_autorizaciones (invoice_number, credito_authorized, credito_authorized_by, credito_authorized_at)
                            VALUES (?, ?, ?, ?);
                        END
                    """
                    auth_bit = 1 if authorized else 0
                    conn.exec_driver_sql(query, (auth_bit, by, at, invoice_number, invoice_number, auth_bit, by, at))
            except Exception as e:
                logger.error(f"Error saving credito auth to SQL: {e}")
        return True

    def mark_revoked_from_relacion(self, invoice_number: int, was_revoked: bool):  # pragma: no cover
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["credito_revoked_from_relacion"] = was_revoked
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE seguimiento_credito_autorizaciones 
                        SET credito_revoked_from_relacion = ?, updated_at = GETDATE()
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO seguimiento_credito_autorizaciones (invoice_number, credito_revoked_from_relacion)
                            VALUES (?, ?);
                        END
                    """
                    bit_val = 1 if was_revoked else 0
                    conn.exec_driver_sql(query, (bit_val, invoice_number, invoice_number, bit_val))
            except Exception as e:
                logger.error(f"Error saving revoked_from_relacion: {e}")
        return True

    def save_credito_notes(self, invoice_number: int, notes: str):  # pragma: no cover
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["credito_notes"] = notes
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE seguimiento_credito_autorizaciones 
                        SET credito_notes = ?, updated_at = GETDATE()
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO seguimiento_credito_autorizaciones (invoice_number, credito_notes)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (notes, invoice_number, invoice_number, notes))
            except Exception as e:
                logger.error(f"Error saving credito notes: {e}")
        return True

    def get_daily_order(self, date_str: str):
        # Try SQL first
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    query = "SELECT manual_order_json FROM factura_daily_order WHERE order_date = ?"
                    result = conn.exec_driver_sql(query, (date_str,)).fetchone()
                    if result and result[0]:
                        order = json.loads(result[0])
                        self.local_daily_orders[date_str] = order  # pragma: no cover
                        self._save_daily_fallback()  # pragma: no cover
                        return order  # pragma: no cover
            except Exception as e:
                logger.error(f"Error fetching daily order: {e}")
        
        # Fallback
        return self.local_daily_orders.get(date_str, [])

    def save_daily_order(self, date_str: str, manual_order: list):
        self.local_daily_orders[date_str] = manual_order
        self._save_daily_fallback()
        
        if self.db_client.engine:
            try:
                order_json = json.dumps(manual_order)
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE factura_daily_order 
                        SET manual_order_json = ?
                        WHERE order_date = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO factura_daily_order (order_date, manual_order_json)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (order_json, date_str, date_str, order_json))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving daily order to SQL: {e}")
        return True

    def get_daily_extras(self, date_str: str):
        # Try SQL first
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    query = "SELECT extra_invoices_json FROM factura_daily_extra WHERE order_date = ?"
                    result = conn.exec_driver_sql(query, (date_str,)).fetchone()
                    if result and result[0]:
                        extras = json.loads(result[0])
                        self.local_daily_extras[date_str] = extras  # pragma: no cover
                        self._save_extra_fallback()  # pragma: no cover
                        return extras  # pragma: no cover
            except Exception as e:
                logger.error(f"Error fetching daily extras: {e}")
        
        # Fallback
        return self.local_daily_extras.get(date_str, [])

    def save_daily_extras(self, date_str: str, extra_invoices: list):
        self.local_daily_extras[date_str] = extra_invoices
        self._save_extra_fallback()
        
        if self.db_client.engine:
            try:
                extras_json = json.dumps(extra_invoices)
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE factura_daily_extra 
                        SET extra_invoices_json = ?
                        WHERE order_date = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO factura_daily_extra (order_date, extra_invoices_json)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (extras_json, date_str, date_str, extras_json))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving daily extras to SQL: {e}")
        return True

    def save_override(self, invoice_number: int, override_category: str):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["category"] = override_category
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE {self.TABLE_NAME} 
                        SET override_category = ?
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO {self.TABLE_NAME} (invoice_number, override_category)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (override_category, int(invoice_number), int(invoice_number), override_category))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving override for invoice {invoice_number} to SQL: {e}")
        return True

    def save_color(self, invoice_number: int, color: str):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["color"] = color
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE {self.TABLE_NAME} 
                        SET color = ?
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO {self.TABLE_NAME} (invoice_number, color)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (color, int(invoice_number), int(invoice_number), color))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving color for invoice {invoice_number} to SQL: {e}")
        return True

    def save_custom_customer_name(self, invoice_number: int, custom_name: str):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):  # pragma: no cover
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["custom_customer_name"] = custom_name
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE {self.TABLE_NAME} 
                        SET custom_customer_name = ?
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO {self.TABLE_NAME} (invoice_number, custom_customer_name)
                            VALUES (?, ?);
                        END
                    """
                    conn.exec_driver_sql(query, (custom_name or None, int(invoice_number), int(invoice_number), custom_name or None))
            except Exception as e:  # pragma: no cover
                logger.error(f"Error saving custom customer name for invoice {invoice_number} to SQL: {e}")
        return True

    def save_sent_to_credito(self, invoice_number: int, sent: bool):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": "", "custom_customer_name": ""}
        self.local_metadata[inv_str]["sent_to_credito"] = sent
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = """
                        UPDATE seguimiento_credito_autorizaciones 
                        SET sent_to_credito = ?, updated_at = GETDATE()
                        WHERE invoice_number = ?;

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO seguimiento_credito_autorizaciones (invoice_number, sent_to_credito)
                            VALUES (?, ?);
                        END
                    """
                    bit_val = 1 if sent else 0
                    conn.exec_driver_sql(query, (bit_val, invoice_number, invoice_number, bit_val))
            except Exception as e:
                logger.error(f"Error saving sent_to_credito: {e}")
        return True
