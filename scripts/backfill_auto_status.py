#!/usr/bin/env python3
"""One-time backfill: auto-transition orders based on SAP delivery notes & invoices.

Checks ALL tracked orders (not just the last 50) and transitions:
  - Pendiente / En Proceso  +  delivery note (ODLN)  →  Entregado
  - Entregado               +  invoice      (OINV)  →  Facturacion

Usage:
    python scripts/backfill_auto_status.py [--dry-run]
"""

import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on the path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

os.environ["WERKZEUG_RUN_MAIN"] = "true"

from dotenv import load_dotenv
load_dotenv()

from hdbcli import dbapi

SCHEMA = os.environ.get("SAP_SCHEMA", "SBO_QUIMICABOSS")
DRY_RUN = "--dry-run" in sys.argv


def main():
    print("=" * 70)
    print("  Open-OMS — Auto-Status Backfill")
    print(f"  Mode: {'DRY RUN (no changes)' if DRY_RUN else 'LIVE (will update orders)'}")
    print("=" * 70)

    # ── Load local order database ─────────────────────────────────────
    db_path = os.path.join(PROJECT_ROOT, "core", "order_status_db.json")
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    orders = db.get("orders", {})
    print(f"\nLoaded {len(orders)} orders from local database.")

    # ── Connect to SAP HANA ───────────────────────────────────────────
    print(f"Connecting to SAP HANA at {os.environ.get('SAP_HOST', '20.0.1.9')}...")
    conn = dbapi.connect(
        address=os.environ.get("SAP_HOST", "20.0.1.9"),
        port=int(os.environ.get("SAP_PORT", "30015")),
        user=os.environ.get("SAP_USER", "SYSTEM"),
        password=os.environ.get("SAP_PASS", ""),
        timeout=10,
        connectTimeout=10000,
    )
    cursor = conn.cursor()
    print("Connected to SAP HANA.")

    # ── Step 1: Get doc_entry for all tracked orders ──────────────────
    all_oids = [oid for oid in orders.keys() if oid.isdigit()]
    print(f"\nStep 1: Looking up doc_entry for {len(all_oids)} orders...")

    oid_to_entry = {}
    chunk_size = 500
    for i in range(0, len(all_oids), chunk_size):
        chunk = all_oids[i: i + chunk_size]
        placeholders = ",".join(["?" for _ in chunk])
        cursor.execute(f"""
            SELECT "DocNum", "DocEntry"
            FROM "{SCHEMA}"."ORDR"
            WHERE "DocNum" IN ({placeholders})
        """, [int(x) for x in chunk])
        for row in cursor.fetchall():
            oid_to_entry[str(int(row[0]))] = int(row[1])

    print(f"  Found {len(oid_to_entry)} orders in SAP.")

    # ── Step 2: Check delivery notes for En Proceso / Pendiente ──────
    eligible_terminado = {
        oid: entry for oid, entry in oid_to_entry.items()
        if orders[oid].get("status") in ("Pendiente", "En Proceso")
    }
    print(f"\nStep 2: Checking delivery notes for {len(eligible_terminado)} orders at Pendiente/En Proceso...")

    terminado_transitions = []
    if eligible_terminado:
        entries = list(eligible_terminado.values())
        entry_to_oid = {v: k for k, v in eligible_terminado.items()}

        for i in range(0, len(entries), chunk_size):
            chunk = entries[i: i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])
            cursor.execute(f"""
                SELECT DISTINCT L1."BaseEntry", D0."DocNum", D0."DocDate"
                FROM "{SCHEMA}"."ODLN" D0
                INNER JOIN "{SCHEMA}"."DLN1" L1 ON D0."DocEntry" = L1."DocEntry"
                WHERE L1."BaseType" = 17 AND L1."BaseEntry" IN ({placeholders})
            """, chunk)
            for row in cursor.fetchall():
                entry = int(row[0])
                oid = entry_to_oid.get(entry)
                if oid:
                    terminado_transitions.append({
                        "order_id": oid,
                        "delivery_num": int(row[1]),
                        "delivery_date": str(row[2]),
                        "previous_status": orders[oid]["status"],
                        "doc_entry": entry,
                    })

    print(f"  Found {len(terminado_transitions)} orders with delivery notes -> Entregado")

    # ── Step 3: Check invoices for Entregado orders ───────────────────
    # Include both existing Entregado AND those we're about to transition
    will_be_terminado = set(t["order_id"] for t in terminado_transitions)
    eligible_factura = {
        oid: entry for oid, entry in oid_to_entry.items()
        if (orders[oid].get("status") == "Entregado" or oid in will_be_terminado)
        and not orders[oid].get("factura_number")
    }
    print(f"\nStep 3: Checking invoices for {len(eligible_factura)} orders at/becoming Entregado...")

    factura_transitions = []
    if eligible_factura:
        entries = list(eligible_factura.values())
        entry_to_oid = {v: k for k, v in eligible_factura.items()}

        for i in range(0, len(entries), chunk_size):
            chunk = entries[i: i + chunk_size]
            placeholders = ",".join(["?" for _ in chunk])
            cursor.execute(f"""
                SELECT DISTINCT I1."BaseEntry", I0."DocNum"
                FROM "{SCHEMA}"."OINV" I0
                INNER JOIN "{SCHEMA}"."INV1" I1 ON I0."DocEntry" = I1."DocEntry"
                WHERE I1."BaseType" = 17 AND I1."BaseEntry" IN ({placeholders})
            """, chunk)
            for row in cursor.fetchall():
                entry = int(row[0])
                oid = entry_to_oid.get(entry)
                if oid:
                    factura_transitions.append({
                        "order_id": oid,
                        "invoice_num": int(row[1]),
                        "doc_entry": entry,
                    })

    print(f"  Found {len(factura_transitions)} orders with invoices -> Facturacion")

    cursor.close()
    conn.close()

    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Entregado transitions:   {len(terminado_transitions)}")
    print(f"  Facturacion transitions: {len(factura_transitions)}")
    print(f"  Total changes:           {len(terminado_transitions) + len(factura_transitions)}")

    if DRY_RUN:
        print(f"\n  [DRY RUN] No changes will be made.\n")
        for t in terminado_transitions[:10]:
            print(f"    #{t['order_id']}: {t['previous_status']} -> Entregado (delivery #{t['delivery_num']})")
        if len(terminado_transitions) > 10:
            print(f"    ... and {len(terminado_transitions) - 10} more")
        for t in factura_transitions[:10]:
            prev = "Entregado" if t["order_id"] in will_be_terminado else orders[t["order_id"]]["status"]
            print(f"    #{t['order_id']}: {prev} -> Facturacion (invoice #{t['invoice_num']})")
        return

    import datetime
    now_iso = datetime.datetime.now().isoformat()
    changed = 0

    # Apply Entregado transitions
    for t in terminado_transitions:
        oid = t["order_id"]
        order = orders[oid]
        old_status = order["status"]
        order["status"] = "Entregado"
        order["last_updated"] = now_iso
        order["doc_entry"] = t["doc_entry"]
        order.setdefault("status_history", []).append({
            "status": "Entregado",
            "previous_status": old_status,
            "timestamp": now_iso,
            "user": "system",
            "notes": f"Backfill auto: Nota de entrega #{t['delivery_num']} detectada en SAP",
        })
        changed += 1
        print(f"  [OK] #{oid}: {old_status} -> Entregado (delivery #{t['delivery_num']})")

    # Apply Facturacion transitions
    for t in factura_transitions:
        oid = t["order_id"]
        order = orders[oid]
        old_status = order["status"]
        order["status"] = "Facturacion"
        order["last_updated"] = now_iso
        order["factura_number"] = str(t["invoice_num"])
        order["doc_entry"] = t["doc_entry"]
        order.setdefault("status_history", []).append({
            "status": "Facturacion",
            "previous_status": old_status,
            "timestamp": now_iso,
            "user": "system",
            "notes": f"Backfill auto: Factura #{t['invoice_num']} detectada en SAP",
        })
        changed += 1
        print(f"  [OK] #{oid}: {old_status} -> Facturacion (invoice #{t['invoice_num']})")

    # Save
    if changed > 0:
        db["last_updated"] = now_iso
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved {changed} changes to {db_path}")
    else:
        print("\n  No changes needed.")


if __name__ == "__main__":
    main()
