import os
import json
import logging
import datetime
from core.database_client import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

def migrate_order_status(db_client):
    path = os.path.join(DATA_DIR, "order_status_db.json")
    if not os.path.exists(path):
        logger.info("No order status fallback found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    orders = data.get("orders", {})
    logger.info(f"Loaded {len(orders)} orders from local fallback JSON.")

    inserted, updated = 0, 0
    with db_client.engine.begin() as conn:
        for order_id, o_data in orders.items():
            if o_data.get("customer_code") == "CL1662":
                continue
            status = o_data.get("status", "")
            last_updated = o_data.get("last_updated", "")
            data_str = json.dumps(o_data, ensure_ascii=False)

            # Idempotent merge/insert
            conn.exec_driver_sql(
                """
                MERGE seguimiento_order_status AS target
                USING (VALUES (?, ?, ?, ?)) AS source (order_id, status, last_updated, data)
                ON target.order_id = source.order_id
                WHEN MATCHED THEN UPDATE SET
                    status = source.status,
                    last_updated = source.last_updated,
                    data = source.data
                WHEN NOT MATCHED THEN INSERT (order_id, status, last_updated, data)
                    VALUES (source.order_id, source.status, source.last_updated, source.data);
                """,
                (str(order_id), status, last_updated, data_str)
            )
            inserted += 1

    logger.info(f"Successfully migrated/merged {inserted} order status records.")

def migrate_factura_metadata(db_client):
    path = os.path.join(DATA_DIR, "factura_metadata.json")
    if not os.path.exists(path):
        logger.info("No factura metadata fallback found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    logger.info(f"Loaded {len(metadata)} metadata records from local fallback JSON.")

    migrated_meta = 0
    migrated_auth = 0
    with db_client.engine.begin() as conn:
        for inv_str, v in metadata.items():
            try:
                inv = int(inv_str)
            except ValueError:
                continue

            if not isinstance(v, dict):
                continue

            # 1. Migrate Overrides / Categories / Colors to factura_metadata
            cat = v.get("category")
            col = v.get("color")
            cust_name = v.get("custom_customer_name")

            if any([cat, col, cust_name]):
                conn.exec_driver_sql(
                    """
                    MERGE factura_metadata AS target
                    USING (VALUES (?, ?, ?, ?)) AS source (invoice_number, override_category, color, custom_customer_name)
                    ON target.invoice_number = source.invoice_number
                    WHEN MATCHED THEN UPDATE SET
                        override_category = source.override_category,
                        color = source.color,
                        custom_customer_name = source.custom_customer_name
                    WHEN NOT MATCHED THEN INSERT (invoice_number, override_category, color, custom_customer_name)
                        VALUES (source.invoice_number, source.override_category, source.color, source.custom_customer_name);
                    """,
                    (inv, cat, col, cust_name)
                )
                migrated_meta += 1

            # 2. Migrate Authorizations to seguimiento_credito_autorizaciones
            auth = v.get("credito_authorized")
            by = v.get("credito_authorized_by")
            at = v.get("credito_authorized_at")
            revoked = 1 if v.get("credito_revoked_from_relacion", False) else 0
            notes = v.get("credito_notes", "")
            sent = 1 if v.get("sent_to_credito", False) else 0

            if any([auth is not None, by, at, revoked, notes, sent]):
                auth_val = 1 if auth else 0
                conn.exec_driver_sql(
                    """
                    MERGE seguimiento_credito_autorizaciones AS target
                    USING (VALUES (?, ?, ?, ?, ?, ?, ?)) AS source 
                        (invoice_number, credito_authorized, credito_authorized_by, 
                         credito_authorized_at, credito_revoked_from_relacion, credito_notes, sent_to_credito)
                    ON target.invoice_number = source.invoice_number
                    WHEN MATCHED THEN UPDATE SET
                        credito_authorized = source.credito_authorized,
                        credito_authorized_by = source.credito_authorized_by,
                        credito_authorized_at = source.credito_authorized_at,
                        credito_revoked_from_relacion = source.credito_revoked_from_relacion,
                        credito_notes = source.credito_notes,
                        sent_to_credito = source.sent_to_credito
                    WHEN NOT MATCHED THEN INSERT 
                        (invoice_number, credito_authorized, credito_authorized_by, 
                         credito_authorized_at, credito_revoked_from_relacion, credito_notes, sent_to_credito)
                        VALUES (source.invoice_number, source.credito_authorized, source.credito_authorized_by, 
                                source.credito_authorized_at, source.credito_revoked_from_relacion, 
                                source.credito_notes, source.sent_to_credito);
                    """,
                    (inv, auth_val, by, at, revoked, notes, sent)
                )
                migrated_auth += 1

    logger.info(f"Migrated {migrated_meta} metadata overrides and {migrated_auth} authorizations.")

def migrate_relacion_envios(db_client):
    path = os.path.join(DATA_DIR, "relacion_envios.json")
    if not os.path.exists(path):
        logger.info("No relacion envios fallback found.")
        return

    with open(path, "r", encoding="utf-8") as f:
        relaciones = json.load(f)
    logger.info(f"Loaded {len(relaciones)} folios from local fallback JSON.")

    migrated_parents = 0
    migrated_childs = 0
    with db_client.engine.begin() as conn:
        for folio, r in relaciones.items():
            rel_date = r.get("relacion_date", "")
            created_at = r.get("created_at")
            updated_at = r.get("updated_at")
            created_by = r.get("created_by")
            updated_by = r.get("updated_by")
            invoices = r.get("invoices", [])
            invoices_json = json.dumps(invoices, ensure_ascii=False)
            inv_nums = ",".join([str(i.get("invoice_number", "")) for i in invoices])
            status = r.get("status", "active")
            is_closed = 1 if r.get("is_closed") else 0
            rolled_from = r.get("rolled_from")
            notes = r.get("notes")
            sigs = json.dumps(r.get("signatures", {}), ensure_ascii=False)

            # Insert/Merge parent Relation
            conn.exec_driver_sql(
                """
                MERGE seguimiento_relacion_envios AS target
                USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) AS source
                    (folio, relacion_date, created_at, updated_at, created_by, updated_by,
                     invoices_json, invoice_numbers, status, is_closed, rolled_from, notes, signatures_json)
                ON target.folio = source.folio
                WHEN MATCHED THEN UPDATE SET
                    relacion_date = source.relacion_date,
                    created_by = source.created_by,
                    updated_by = source.updated_by,
                    invoices_json = source.invoices_json,
                    invoice_numbers = source.invoice_numbers,
                    status = source.status,
                    is_closed = source.is_closed,
                    rolled_from = source.rolled_from,
                    notes = source.notes,
                    signatures_json = source.signatures_json
                WHEN NOT MATCHED THEN INSERT 
                    (folio, relacion_date, created_at, updated_at, created_by, updated_by,
                     invoices_json, invoice_numbers, status, is_closed, rolled_from, notes, signatures_json)
                    VALUES (source.folio, source.relacion_date, source.created_at, source.updated_at,
                            source.created_by, source.updated_by, source.invoices_json, source.invoice_numbers,
                            source.status, source.is_closed, source.rolled_from, source.notes, source.signatures_json);
                """,
                (folio, rel_date, created_at, updated_at, created_by, updated_by,
                 invoices_json, inv_nums, status, is_closed, rolled_from, notes, sigs)
            )
            migrated_parents += 1

            # Insert/Merge child Invoices
            for inv in invoices:
                inv_num = str(inv.get("invoice_number", ""))
                if not inv_num:
                    continue
                is_checked = 1 if inv.get("_selected", True) else 0
                ship_type = inv.get("shipping_type", "LOCAL")
                obs = inv.get("observaciones", inv.get("nota", ""))
                data_json = json.dumps(inv, ensure_ascii=False)

                conn.exec_driver_sql(
                    """
                    MERGE seguimiento_relacion_invoices AS target
                    USING (VALUES (?, ?, ?, ?, ?, ?)) AS source
                        (folio, invoice_number, is_checked, shipping_type, observaciones, data_json)
                    ON target.folio = source.folio AND target.invoice_number = source.invoice_number
                    WHEN MATCHED THEN UPDATE SET
                        is_checked = source.is_checked,
                        shipping_type = source.shipping_type,
                        observaciones = source.observaciones,
                        data_json = source.data_json
                    WHEN NOT MATCHED THEN INSERT 
                        (folio, invoice_number, is_checked, shipping_type, observaciones, data_json)
                        VALUES (source.folio, source.invoice_number, source.is_checked, source.shipping_type,
                                source.observaciones, source.data_json);
                    """,
                    (folio, inv_num, is_checked, ship_type, obs, data_json)
                )
                migrated_childs += 1

    logger.info(f"Migrated {migrated_parents} relations and {migrated_childs} relation invoices.")

def main():
    client = DatabaseClient()
    if not client.connect():
        logger.error("Failed to connect to database. Check your .env configuration.")
        return
    
    logger.info("Connected to database. Starting migration...")
    
    # Run migrations
    migrate_order_status(client)
    migrate_factura_metadata(client)
    migrate_relacion_envios(client)
    
    logger.info("Migration completed successfully.")

if __name__ == "__main__":
    main()
