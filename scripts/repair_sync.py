"""
repair_sync_v2.py — Phase 4: One-Time Data Repair (using direct UPDATE)
=========================================================================
Uses simple UPDATE statements instead of MERGE to avoid any issues.
"""

import pyodbc
import json
import sys
import datetime
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=192.168.2.237;"
    "DATABASE=SGA_Database;"
    "UID=sga_app_user;"
    "PWD=QuimicaBoss_2026!;"
    "TrustServerCertificate=yes;"
)

SAO_TABLE = "seguimiento_order_status"
SGA_TABLE = "order_status"

STATUS_MIGRATIONS = {
    "Preparando": "Entregado",
    "Preparado": "Entregado",
    "Terminado": "Entregado",
    "Listo para Env\u00edo": "Relacion de envio",
    "Listo para Envio": "Relacion de envio",
    "Entregado a almacen": "Relacion de envio",
    "Recibido por almacen": "Relacion de envio",
    "Relaci\u00f3n de env\u00edo": "Relacion de envio",
    "Enviado": "Enviado al cliente",
    "Recibido por cliente": "Enviado al cliente",
    "Cerrado en SAP": "__NEEDS_RECONCILE__",
}

COMMIT = "--commit" in sys.argv


def load_table(cursor, table_name):
    cursor.execute(f"SELECT order_id, status, last_updated, data FROM {table_name}")
    rows = cursor.fetchall()
    orders = {}
    for row in rows:
        oid = str(row[0])
        try:
            data = json.loads(row[3]) if row[3] else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        orders[oid] = {
            "status": row[1] or "",
            "last_updated": row[2] or "",
            "data": data,
        }
    return orders


def reconcile_cerrado(order_data):
    data = order_data.get("data", {})
    has_factura = bool(data.get("factura_number"))
    return "Facturacion" if has_factura else "Entregado"


try:
    conn = pyodbc.connect(CONN_STR, timeout=10)
    cursor = conn.cursor()

    mode = "COMMIT MODE" if COMMIT else "DRY RUN"
    print("=" * 80)
    print(f"  PHASE 4: DATA REPAIR v2 — {mode}")
    print("=" * 80)

    sao_orders = load_table(cursor, SAO_TABLE)
    sga_orders = load_table(cursor, SGA_TABLE)
    print(f"\n  SAO: {len(sao_orders)}  |  SGA: {len(sga_orders)}")

    # Build the list of all updates needed for each table
    # Format: (order_id, new_status, new_data_json)
    sao_updates = {}  # oid -> (new_status, new_data)
    sga_updates = {}

    now_iso = datetime.datetime.now().isoformat()

    # Step 2: Label migration
    for oid, order in sao_orders.items():
        old = order["status"]
        new = STATUS_MIGRATIONS.get(old, old)
        if new == "__NEEDS_RECONCILE__":
            new = reconcile_cerrado(order)
        if new != old:
            order["status"] = new
            order["data"]["status"] = new
            sao_updates[oid] = order

    for oid, order in sga_orders.items():
        old = order["status"]
        new = STATUS_MIGRATIONS.get(old, old)
        if new == "__NEEDS_RECONCILE__":
            new = reconcile_cerrado(order)
        if new != old:
            order["status"] = new
            order["data"]["status"] = new
            sga_updates[oid] = order

    label_sao = len(sao_updates)
    label_sga = len(sga_updates)

    # Step 3: Authority sync (SGA <- SAO)
    both_keys = set(sga_orders.keys()) & set(sao_orders.keys())
    authority_count = 0
    for oid in both_keys:
        if sga_orders[oid]["status"] != sao_orders[oid]["status"]:
            sga_orders[oid]["status"] = sao_orders[oid]["status"]
            sga_orders[oid]["data"]["status"] = sao_orders[oid]["status"]
            sga_updates[oid] = sga_orders[oid]
            authority_count += 1

    # Step 4: SGA-only reconciliation
    sga_only = set(sga_orders.keys()) - set(sao_orders.keys())
    reconciled = 0
    for oid in sga_only:
        order = sga_orders[oid]
        sap_status = order["data"].get("sap_status", "")
        status = order["status"]
        new_status = None

        if sap_status == "Cerrado":
            has_factura = bool(order["data"].get("factura_number"))
            if has_factura:
                if status not in ["Facturacion", "Relacion de envio", "Enviado al cliente"]:
                    new_status = "Facturacion"
            else:
                if status not in ["Entregado", "Facturacion", "Relacion de envio", "Enviado al cliente"]:
                    new_status = "Entregado"
        elif sap_status == "Cancelado" and status != "Cancelado":
            new_status = "Cancelado"

        if new_status:
            order["status"] = new_status
            order["data"]["status"] = new_status
            sga_updates[oid] = order
            reconciled += 1

    print(f"\n  Label migrations:   SAO={label_sao}, SGA={label_sga}")
    print(f"  Authority sync:     {authority_count}")
    print(f"  SGA-only reconcile: {reconciled}")
    print(f"  Total SAO updates:  {len(sao_updates)}")
    print(f"  Total SGA updates:  {len(sga_updates)}")

    # Predicted sync rate
    matches = sum(1 for oid in both_keys if sga_orders[oid]["status"] == sao_orders[oid]["status"])
    print(f"\n  Predicted sync: {matches}/{len(both_keys)} = {matches/len(both_keys)*100:.1f}%")

    if COMMIT:
        print(f"\n{'─' * 80}")
        print("  WRITING...")
        print(f"{'─' * 80}")

        # Write SAO updates using UPDATE (not MERGE)
        written = 0
        for oid, order in sao_updates.items():
            order["data"]["last_updated"] = now_iso
            order["data"]["repair_note"] = "Phase 4"
            data_json = json.dumps(order["data"], ensure_ascii=False)
            cursor.execute(
                f"UPDATE {SAO_TABLE} SET status=?, last_updated=?, data=? WHERE order_id=?",
                (order["status"], now_iso, data_json, oid)
            )
            written += cursor.rowcount
        conn.commit()
        print(f"  [OK] SAO: {written} rows updated")

        # Write SGA updates using UPDATE
        written = 0
        batch_size = 100
        oids = list(sga_updates.keys())
        for i in range(0, len(oids), batch_size):
            batch = oids[i:i+batch_size]
            for oid in batch:
                order = sga_updates[oid]
                order["data"]["last_updated"] = now_iso
                order["data"]["repair_note"] = "Phase 4"
                data_json = json.dumps(order["data"], ensure_ascii=False)
                cursor.execute(
                    f"UPDATE {SGA_TABLE} SET status=?, last_updated=?, data=? WHERE order_id=?",
                    (order["status"], now_iso, data_json, oid)
                )
                written += cursor.rowcount
            conn.commit()
            print(f"    batch {i//batch_size + 1}: {len(batch)} rows committed")

        print(f"  [OK] SGA: {written} rows updated")

        # Verify immediately
        cursor.execute(f"SELECT COUNT(*) FROM {SGA_TABLE} WHERE status = 'Cerrado en SAP'")
        remaining = cursor.fetchone()[0]
        print(f"\n  Verify: 'Cerrado en SAP' remaining in SGA = {remaining}")

        cursor.execute(f"""
            SELECT 
                SUM(CASE WHEN s.status = o.status THEN 1 ELSE 0 END) as matches,
                COUNT(*) as total
            FROM {SAO_TABLE} s
            INNER JOIN {SGA_TABLE} o ON s.order_id = o.order_id
        """)
        row = cursor.fetchone()
        print(f"  Verify: Sync rate = {row[0]}/{row[1]} = {row[0]/row[1]*100:.1f}%")

        print(f"\n{'=' * 80}")
        print(f"  REPAIR COMPLETE")
        print(f"{'=' * 80}")
    else:
        print(f"\n  DRY RUN — run with --commit to apply")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"[FAIL] {e}")
    import traceback
    traceback.print_exc()
