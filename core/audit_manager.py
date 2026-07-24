import logging
import json
from datetime import datetime
from core.database_client import DatabaseClient
from sqlalchemy import text

logger = logging.getLogger(__name__)

class AuditManager:
    TABLE_NAME = "audit_logs"

    def __init__(self, db_client=None):
        if db_client is not None:
            self.db_client = db_client
        else:
            self.db_client = DatabaseClient()
            self.db_client.connect()
        self._ensure_table_exists()
        self._cleanup_old_logs()

    def _ensure_table_exists(self):  # pragma: no cover
        try:
            if not self.db_client.engine:
                return

            check_query = f"""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.TABLE_NAME}' and xtype='U')
                BEGIN
                    CREATE TABLE {self.TABLE_NAME} (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        timestamp DATETIME NOT NULL,
                        username VARCHAR(100) NOT NULL,
                        action_type VARCHAR(100) NOT NULL,
                        entity_id VARCHAR(100) NULL,
                        details NVARCHAR(MAX) NULL,
                        ip_address VARCHAR(50) NULL
                    )
                END
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(check_query)
            logger.info(f"Verified {self.TABLE_NAME} table exists")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to verify/create {self.TABLE_NAME} table: {e}")

    def _cleanup_old_logs(self):  # pragma: no cover
        """Deletes logs older than 3 months"""
        try:
            if not self.db_client.engine:
                return
            cleanup_query = f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE timestamp < DATEADD(month, -3, GETDATE())
            """
            with self.db_client.engine.begin() as conn:
                conn.exec_driver_sql(cleanup_query)
            logger.info(f"Cleaned up old audit logs (>3 months)")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to cleanup old audit logs: {e}")

    def log_action(self, username: str, action_type: str, entity_id: str = None, details: dict = None, ip_address: str = None):  # pragma: no cover
        try:
            if not self.db_client.engine:
                return
            
            details_json = json.dumps(details) if details else None
            insert_query = text(f"""
                INSERT INTO {self.TABLE_NAME} (timestamp, username, action_type, entity_id, details, ip_address)
                VALUES (:timestamp, :username, :action_type, :entity_id, :details, :ip_address)
            """)
            
            with self.db_client.engine.begin() as conn:
                conn.execute(insert_query, {
                    "timestamp": datetime.now(),
                    "username": username or "system",
                    "action_type": action_type,
                    "entity_id": str(entity_id) if entity_id else None,
                    "details": details_json,
                    "ip_address": ip_address
                })
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to log audit action {action_type}: {e}")

    def get_logs(self, limit=1000):  # pragma: no cover
        try:
            if not self.db_client.engine:
                return []
            
            query = text(f"""
                SELECT TOP (:limit) id, timestamp, username, action_type, entity_id, details, ip_address
                FROM {self.TABLE_NAME}
                ORDER BY timestamp DESC
            """)
            
            with self.db_client.engine.connect() as conn:
                result = conn.execute(query, {"limit": limit})
                logs = []
                for row in result:
                    logs.append({
                        "id": row.id,
                        "timestamp": row.timestamp.strftime("%Y-%m-%d %H:%M:%S") if row.timestamp else None,
                        "username": row.username,
                        "action_type": row.action_type,
                        "entity_id": row.entity_id,
                        "details": json.loads(row.details) if row.details else None,
                        "ip_address": row.ip_address
                    })
                return logs
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to fetch audit logs: {e}")
            return []
