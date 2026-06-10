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
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "factura_metadata.json")
        self.db_path = db_path
        self.local_metadata = {}
        self.local_daily_orders = {}

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
                        color VARCHAR(20) NULL
                    )
                END
                ELSE
                BEGIN
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{self.TABLE_NAME}') AND name = 'color')
                    BEGIN
                        ALTER TABLE {self.TABLE_NAME} ADD color VARCHAR(20) NULL;
                        ALTER TABLE {self.TABLE_NAME} ALTER COLUMN override_category VARCHAR(50) NULL;
                    END
                END
                
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='factura_daily_order' and xtype='U')
                BEGIN
                    CREATE TABLE factura_daily_order (
                        order_date VARCHAR(20) PRIMARY KEY,
                        manual_order_json VARCHAR(MAX) NULL
                    )
                END
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(check_query)
            logger.info(f"Verified tables exist")
        except Exception as e:
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
            except Exception:
                self.local_daily_orders = {}

    def _save_fallback(self):
        """Saves metadata to JSON file fallback"""
        try:
            dir_name = os.path.dirname(self.db_path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.local_metadata, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.db_path)
        except Exception as e:
            logger.error(f"Error saving JSON fallback: {e}")

    def _save_daily_fallback(self):
        try:
            daily_path = os.path.join(os.path.dirname(self.db_path), "factura_daily_order.json")
            dir_name = os.path.dirname(self.db_path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.local_daily_orders, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, daily_path)
        except Exception as e:
            logger.error(f"Error saving daily order JSON fallback: {e}")

    def get_overrides(self):
        """Returns (overrides_dict, colors_dict)"""
        overrides = {}
        colors = {}
        # 1. Load from local fallback first
        for k, v in self.local_metadata.items():
            try:
                if isinstance(v, dict):
                    if v.get("category"): overrides[int(k)] = v.get("category")
                    if v.get("color"): colors[int(k)] = v.get("color")
                else:
                    overrides[int(k)] = v
            except ValueError:
                pass
                
        # 2. Try to load from SQL Server and merge
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    result = conn.exec_driver_sql(f"SELECT invoice_number, override_category, color FROM {self.TABLE_NAME}").fetchall()
                    for row in result:
                        inv, cat, col = row[0], row[1], row[2]
                        if cat: overrides[inv] = cat
                        if col: colors[inv] = col
                        self.local_metadata[str(inv)] = {"category": cat or "", "color": col or ""}
                    self._save_fallback()
            except Exception as e:
                logger.error(f"Error fetching factura metadata from SQL: {e}")
                
        return overrides, colors

    def get_daily_order(self, date_str: str):
        # Try SQL first
        if self.db_client.engine:
            try:
                with self.db_client.engine.connect() as conn:
                    query = f"SELECT manual_order_json FROM factura_daily_order WHERE order_date = '{date_str.replace(chr(39), chr(39)+chr(39))}'"
                    result = conn.exec_driver_sql(query).fetchone()
                    if result and result[0]:
                        order = json.loads(result[0])
                        self.local_daily_orders[date_str] = order
                        self._save_daily_fallback()
                        return order
            except Exception as e:
                logger.error(f"Error fetching daily order: {e}")
        
        # Fallback
        return self.local_daily_orders.get(date_str, [])

    def save_daily_order(self, date_str: str, manual_order: list):
        self.local_daily_orders[date_str] = manual_order
        self._save_daily_fallback()
        
        if self.db_client.engine:
            try:
                order_json = json.dumps(manual_order).replace("'", "''")
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE factura_daily_order 
                        SET manual_order_json = '{order_json}'
                        WHERE order_date = '{date_str.replace("'", "''")}';

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO factura_daily_order (order_date, manual_order_json)
                            VALUES ('{date_str.replace("'", "''")}', '{order_json}');
                        END
                    """
                    conn.exec_driver_sql(query)
            except Exception as e:
                logger.error(f"Error saving daily order to SQL: {e}")
        return True

    def save_override(self, invoice_number: int, override_category: str):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": ""}
        self.local_metadata[inv_str]["category"] = override_category
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE {self.TABLE_NAME} 
                        SET override_category = '{override_category.replace("'", "''")}'
                        WHERE invoice_number = {int(invoice_number)};

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO {self.TABLE_NAME} (invoice_number, override_category)
                            VALUES ({int(invoice_number)}, '{override_category.replace("'", "''")}');
                        END
                    """
                    conn.exec_driver_sql(query)
            except Exception as e:
                logger.error(f"Error saving override for invoice {invoice_number} to SQL: {e}")
        return True

    def save_color(self, invoice_number: int, color: str):
        inv_str = str(invoice_number)
        if inv_str not in self.local_metadata or not isinstance(self.local_metadata[inv_str], dict):
            self.local_metadata[inv_str] = {"category": "", "color": ""}
        self.local_metadata[inv_str]["color"] = color
        self._save_fallback()
        
        if self.db_client.engine:
            try:
                with self.db_client.engine.begin() as conn:
                    query = f"""
                        UPDATE {self.TABLE_NAME} 
                        SET color = '{color.replace("'", "''")}'
                        WHERE invoice_number = {int(invoice_number)};

                        IF @@ROWCOUNT = 0
                        BEGIN
                            INSERT INTO {self.TABLE_NAME} (invoice_number, color)
                            VALUES ({int(invoice_number)}, '{color.replace("'", "''")}');
                        END
                    """
                    conn.exec_driver_sql(query)
            except Exception as e:
                logger.error(f"Error saving color for invoice {invoice_number} to SQL: {e}")
        return True
