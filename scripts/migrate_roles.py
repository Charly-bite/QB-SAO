"""
scripts/migrate_roles.py
========================
One-time migration:
  - billing  ->  facturacion  (everyone except the credito list)
  - billing  ->  credito      (RubenH, AzucenaL)

Run from the QB-SAO PROD root:
    .venv\\Scripts\\python.exe scripts/migrate_roles.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

# Users that should become CREDITO instead of FACTURACION
CREDITO_USERS = {"RubenH", "AzucenaL"}

def main():
    from core.database_client import DatabaseClient

    db = DatabaseClient()
    if not db.connect():
        print("[ERROR] Could not connect to SQL Server.")
        sys.exit(1)

    engine = db.get_sql_engine()

    with engine.connect() as conn:
        # -- Preview current state --------------------------------------------
        rows = conn.exec_driver_sql(
            "SELECT username, role FROM seguimiento_users ORDER BY role, username"
        ).fetchall()

        print("\n[INFO] Current users:")
        print(f"  {'Username':<25} {'Role'}")
        print("  " + "-" * 40)
        billing_users = []
        for username, role in rows:
            marker = " <- will migrate" if role == "billing" else ""
            print(f"  {username:<25} {role}{marker}")
            if role == "billing":
                billing_users.append(username)

        if not billing_users:
            print("\n[OK] No 'billing' users found -- migration not needed.")
            return

        print("\n[PLAN] Migration plan:")
        for u in billing_users:
            target = "credito" if u in CREDITO_USERS else "facturacion"
            print(f"    {u:<25} billing  ->  {target}")

        confirm = input("\n[WARN] Proceed with migration? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # -- Execute migration ----------------------------------------------------
    with engine.begin() as conn:
        # Move credito users
        for username in CREDITO_USERS:
            conn.exec_driver_sql(
                "UPDATE seguimiento_users SET role='credito' "
                "WHERE username=? AND role='billing'",
                (username,)
            )

        # Move all remaining billing -> facturacion
        conn.exec_driver_sql(
            "UPDATE seguimiento_users SET role='facturacion' WHERE role='billing'"
        )

    # -- Verify ---------------------------------------------------------------
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT username, role FROM seguimiento_users ORDER BY role, username"
        ).fetchall()

    print("\n[OK] Migration complete! Updated users:")
    print(f"  {'Username':<25} {'Role'}")
    print("  " + "-" * 40)
    for username, role in rows:
        print(f"  {username:<25} {role}")


if __name__ == "__main__":
    main()
