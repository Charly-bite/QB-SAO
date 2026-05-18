"""
Database Client — Open-OMS
Provides SQL Server connectivity via ODBC + SQLAlchemy.
"""

import os
import logging
import pyodbc
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseClient:
    """SQL Server database client for local persistence."""

    def __init__(self):
        self.engine = None
        self.connected = False
        self._connection_string = None

    def _build_connection_string(self):
        driver = os.getenv("SQL_DRIVER", "")
        if not driver:
            try:
                available = [d for d in pyodbc.drivers() if 'SQL Server' in d]
                for preferred in ['ODBC Driver 18 for SQL Server', 'ODBC Driver 17 for SQL Server', 'SQL Server']:
                    if preferred in available:
                        driver = '{' + preferred + '}'
                        break
                if not driver and available:
                    driver = '{' + available[0] + '}'
                if not driver:
                    driver = '{ODBC Driver 17 for SQL Server}'
            except Exception:
                driver = '{ODBC Driver 17 for SQL Server}'
        server = os.getenv("SQL_SERVER", "192.168.2.237")
        database = os.getenv("SQL_DATABASE", "SGA_Database")
        user = os.getenv("SQL_USER", "sga_app_user")
        password = os.getenv("SQL_PASSWORD", "")
        trust = os.getenv("SQL_TRUST_CERTIFICATE", "yes").lower()

        if not password:
            logger.error("CRITICAL: SQL_PASSWORD is empty!")
            raise ValueError("Missing SQL_PASSWORD in environment config.")

        return (
            f"DRIVER={driver};SERVER={server};DATABASE={database};"
            f"UID={user};PWD={password};TrustServerCertificate={trust}"
        )

    def connect(self):
        """Establish connection to SQL Server."""
        try:
            self._connection_string = self._build_connection_string()

            # Test with pyodbc first
            conn = pyodbc.connect(self._connection_string, timeout=10)
            conn.close()

            # Create SQLAlchemy engine
            sa_url = f"mssql+pyodbc:///?odbc_connect={self._connection_string}"
            self.engine = create_engine(sa_url, echo=False, pool_pre_ping=True)

            self.connected = True
            logger.info("✅ SQL Server connected")
            return True

        except Exception as e:
            logger.error(f"❌ SQL Server connection failed: {e}")
            self.connected = False
            self.engine = None
            return False

    def get_sql_engine(self):
        """Get the SQLAlchemy engine."""
        return self.engine

    def execute_query(self, query, params=None):
        """Execute a raw SQL query and return results."""
        if not self.engine:
            raise ConnectionError("Not connected to SQL Server")

        with self.engine.connect() as conn:
            if params:
                result = conn.exec_driver_sql(query, params)
            else:
                result = conn.exec_driver_sql(query)
            return result.fetchall()

