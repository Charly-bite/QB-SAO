"""
Centralized Schema Initializer — Open-OMS
Consolidates all database table creations and column migrations into a single,
sequential bootstrap routine to prevent DDL schema lock deadlocks.
"""

import logging

logger = logging.getLogger(__name__)


def init_db_schema(db_client) -> bool:
    """Initialize all SQL Server tables and columns sequentially."""
    if not db_client or not db_client.engine:
        logger.warning("[SCHEMA] No active SQL engine available for schema initialization.")
        return False

    try:
        with db_client.engine.begin() as conn:
            # 1. seguimiento_users
            conn.exec_driver_sql("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_users' and xtype='U')
                CREATE TABLE seguimiento_users (
                    username VARCHAR(100) PRIMARY KEY,
                    password_hash VARCHAR(256),
                    salt VARCHAR(64),
                    full_name NVARCHAR(200),
                    email VARCHAR(200),
                    role VARCHAR(50) DEFAULT 'viewer',
                    is_active BIT DEFAULT 1,
                    must_change_password BIT DEFAULT 0,
                    last_login VARCHAR(50),
                    created_at VARCHAR(50),
                    warehouse VARCHAR(50) DEFAULT '',
                    sap_seller_name VARCHAR(100) DEFAULT '',
                    signature_path VARCHAR(500) DEFAULT ''
                )
            """)
            try:
                conn.exec_driver_sql("ALTER TABLE seguimiento_users ADD sap_seller_name VARCHAR(100) DEFAULT ''")
            except Exception:
                pass
            try:
                conn.exec_driver_sql("ALTER TABLE seguimiento_users ADD signature_path VARCHAR(500) DEFAULT ''")
            except Exception:
                pass

            # 2. seguimiento_order_status
            conn.exec_driver_sql("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_order_status' and xtype='U')
                CREATE TABLE seguimiento_order_status (
                    order_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(100),
                    last_updated VARCHAR(50),
                    data NVARCHAR(MAX)
                )
            """)

            # 3. factura_metadata and related
            conn.exec_driver_sql("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='factura_metadata' and xtype='U')
                BEGIN
                    CREATE TABLE factura_metadata (
                        invoice_number INT PRIMARY KEY,
                        override_category VARCHAR(50) NULL,
                        color VARCHAR(20) NULL,
                        custom_customer_name VARCHAR(150) NULL
                    )
                END
                ELSE
                BEGIN
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'color')
                    BEGIN
                        ALTER TABLE factura_metadata ADD color VARCHAR(20) NULL;
                        ALTER TABLE factura_metadata ALTER COLUMN override_category VARCHAR(50) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'custom_customer_name')
                    BEGIN
                        ALTER TABLE factura_metadata ADD custom_customer_name VARCHAR(150) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'credito_authorized')
                    BEGIN
                        ALTER TABLE factura_metadata ADD credito_authorized BIT NULL;
                        ALTER TABLE factura_metadata ADD credito_authorized_by VARCHAR(50) NULL;
                        ALTER TABLE factura_metadata ADD credito_authorized_at VARCHAR(50) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'credito_revoked_from_relacion')
                    BEGIN
                        ALTER TABLE factura_metadata ADD credito_revoked_from_relacion BIT NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'credito_notes')
                    BEGIN
                        ALTER TABLE factura_metadata ADD credito_notes VARCHAR(MAX) NULL;
                    END
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('factura_metadata') AND name = 'sent_to_credito')
                    BEGIN
                        ALTER TABLE factura_metadata ADD sent_to_credito BIT NULL;
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
            """)

            # 4. seguimiento_relacion_envios & child
            conn.exec_driver_sql("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_relacion_envios' and xtype='U')
                BEGIN
                    CREATE TABLE seguimiento_relacion_envios (
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

                IF NOT EXISTS (
                    SELECT * FROM sys.columns
                    WHERE object_id = OBJECT_ID('seguimiento_relacion_envios')
                      AND name = 'signatures_json'
                )
                BEGIN
                    ALTER TABLE seguimiento_relacion_envios
                    ADD signatures_json VARCHAR(MAX) NULL
                END

                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='seguimiento_relacion_invoices' and xtype='U')
                BEGIN
                    CREATE TABLE seguimiento_relacion_invoices (
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

                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_relacion_invoices_folio' AND object_id=OBJECT_ID('seguimiento_relacion_invoices'))
                CREATE INDEX IX_relacion_invoices_folio ON seguimiento_relacion_invoices (folio)

                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_relacion_invoices_invoice' AND object_id=OBJECT_ID('seguimiento_relacion_invoices'))
                CREATE INDEX IX_relacion_invoices_invoice ON seguimiento_relacion_invoices (invoice_number)
            """)

            # 5. audit_logs
            conn.exec_driver_sql("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='audit_logs' and xtype='U')
                BEGIN
                    CREATE TABLE audit_logs (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        timestamp DATETIME NOT NULL,
                        username VARCHAR(100) NOT NULL,
                        action_type VARCHAR(100) NOT NULL,
                        entity_id VARCHAR(100) NULL,
                        details NVARCHAR(MAX) NULL,
                        ip_address VARCHAR(50) NULL
                    )
                END
            """)

        logger.info("[SCHEMA] Centralized schema initialization completed successfully.")
        return True
    except Exception as e:
        logger.error(f"[SCHEMA] Schema initialization failed: {e}")
        return False
