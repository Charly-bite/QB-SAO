"""
Database Client — Open-OMS
Provides SQL Server connectivity via ODBC + SQLAlchemy.
"""

import os
import logging
import time
import random
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
        timeout = os.getenv("SQL_TIMEOUT", "5")

        if not password:
            logger.error("CRITICAL: SQL_PASSWORD is empty!")
            raise ValueError("Missing SQL_PASSWORD in environment config.")

        return (
            f"DRIVER={driver};SERVER={server};DATABASE={database};"
            f"UID={user};PWD={password};TrustServerCertificate={trust};"
            f"Connection Timeout={timeout}"
        )

    def connect(self, max_retries=5, retry_delay=2):
        """Establish connection to SQL Server with retries, exponential backoff, and jitter."""
        try:
            self._connection_string = self._build_connection_string()
        except ValueError as e:
            logger.error(f"[ERROR] Cannot build connection string: {e}")
            self.connected = False
            self.engine = None
            return False

        for attempt in range(1, max_retries + 1):
            try:
                # Test with pyodbc first
                timeout_val = int(os.getenv("SQL_TIMEOUT", "5"))
                conn = pyodbc.connect(self._connection_string, timeout=timeout_val)
                conn.close()

                # Create SQLAlchemy engine with pooling settings
                sa_url = f"mssql+pyodbc:///?odbc_connect={self._connection_string}"
                self.engine = create_engine(
                    sa_url,
                    echo=False,
                    pool_pre_ping=True,
                    pool_recycle=1800,  # recycle connections after 30 minutes
                    pool_size=10,       # connection pool size
                    max_overflow=20,    # allowed overflow connections
                    pool_timeout=15     # wait time for connection from pool
                )

                self.connected = True
                logger.info("[OK] SQL Server connected")
                return True

            except Exception as e:
                if attempt < max_retries:
                    # Exponential backoff with jitter
                    backoff = retry_delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, 0.5)
                    sleep_time = backoff + jitter
                    logger.warning(
                        f"[WARN] SQL Server connection attempt {attempt} failed: {e}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(sleep_time)
                else:
                    logger.error(f"[ERROR] SQL Server connection failed after {max_retries} attempts: {e}")

        self.connected = False
        self.engine = None
        return False

    def get_sql_engine(self):
        """Get the SQLAlchemy engine."""
        return self.engine

    def execute_query(self, query, params=None, retries=3, delay=1):
        """Execute a raw SQL query and return results, retrying on transient connection errors."""
        if not self.engine:
            raise ConnectionError("Not connected to SQL Server")

        for attempt in range(1, retries + 1):
            try:
                if not self.engine:
                    logger.info("DatabaseClient: Reconnecting to SQL Server...")
                    self.connect()

                if not self.engine:
                    raise ConnectionError("Not connected to SQL Server")

                with self.engine.connect() as conn:
                    if params:
                        result = conn.exec_driver_sql(query, params)
                    else:
                        result = conn.exec_driver_sql(query)
                    return result.fetchall()
            except Exception as e:
                self.connected = False
                if self.engine:
                    try:
                        self.engine.dispose()
                    except Exception:
                        pass
                    self.engine = None

                if attempt < retries:
                    backoff = delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, 0.2)
                    sleep_time = backoff + jitter
                    logger.warning(
                        f"[WARN] Query execution failed (attempt {attempt}/{retries}): {e}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(sleep_time)
                else:
                    logger.error(f"[ERROR] Query execution failed after {retries} attempts: {e}")
                    raise




