import os
from dotenv import load_dotenv
from hdbcli import dbapi

load_dotenv()

host = os.environ.get("SAP_HOST")
port = int(os.environ.get("SAP_PORT", "30015"))
schema = os.environ.get("SAP_SCHEMA", "SBO_QUIMICABOSS")
user = os.environ.get("SAP_USER")
password = os.environ.get("SAP_PASS")

try:
    conn = dbapi.connect(address=host, port=port, user=user, password=password)
    cursor = conn.cursor()

    # Test 1: Customer master data
    print("=== Test 1: Customer Master Data ===")
    query = f"""
        SELECT
            T0."CardCode",
            T0."CardName",
            T0."CreditLine",
            T0."Balance",
            T0."BalanceDue"
        FROM "{schema}"."OCRD" T0
        WHERE T0."CardCode" = 'CL00182'
    """
    try:
        cursor.execute(query)
        row = cursor.fetchone()
        if row:
            print(f"CardCode: {row[0]}")
            print(f"CardName: {row[1]}")
            print(f"CreditLine: {row[2]}")
            print(f"Balance: {row[3]}")
            print(f"BalanceDue: {row[4]}")
        else:
            print("No rows found")
    except Exception as e:
        print(f"Error in query 1: {e}")
        # Try without BalanceDue
        print("Trying without BalanceDue...")
        query2 = f"""
            SELECT
                T0."CardCode",
                T0."CardName",
                T0."CreditLine",
                T0."Balance"
            FROM "{schema}"."OCRD" T0
            WHERE T0."CardCode" = 'CL00182'
        """
        cursor.execute(query2)
        row = cursor.fetchone()
        if row:
            print(f"CardCode: {row[0]}")
            print(f"CardName: {row[1]}")
            print(f"CreditLine: {row[2]}")
            print(f"Balance: {row[3]}")
        else:
            print("No rows found")

    # Test 2: Open invoices
    print("\n=== Test 2: Open Invoices (first 3) ===")
    inv_query = f"""
        SELECT TOP 3
            T0."DocNum",
            T0."DocDate",
            T0."DocDueDate",
            T0."DocTotal",
            T0."PaidToDate",
            (T0."DocTotal" - T0."PaidToDate") AS "SaldoPendiente",
            T0."DocCur",
            DAYS_BETWEEN(T0."DocDueDate", CURRENT_DATE) AS "DiasRetraso"
        FROM "{schema}"."OINV" T0
        WHERE T0."CardCode" = 'CL00182'
          AND T0."DocStatus" = 'O'
          AND T0."CANCELED" = 'N'
          AND (T0."DocTotal" - T0."PaidToDate") > 0
        ORDER BY T0."DocDueDate" ASC
    """
    cursor.execute(inv_query)
    for row in cursor.fetchall():
        print(f"DocNum: {row[0]} | DueDate: {row[2]} | Balance: {row[5]} {row[6]} | Days: {row[7]}")

    cursor.close()
    conn.close()
    print("\nAll tests passed!")
except Exception as e:
    print(f"Connection error: {e}")
