import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app import create_app

app = create_app()
app.app_context().push()
sap = app.sap_connector
sap.connect()

conn = getattr(sap._local, 'connection', None)
cursor = conn.cursor()
schema = sap.schema

# Get a breakdown of shipping methods for all active open orders (e.g., from the last 30 days)
cursor.execute(f'''
    SELECT T4."TrnspName", COUNT(T0."DocNum") as order_count
    FROM {schema}."ORDR" T0 
    LEFT JOIN {schema}."OSHP" T4 ON T0."TrnspCode" = T4."TrnspCode" 
    WHERE T0."DocStatus" = 'O' AND (T0."CANCELED" = 'N' OR T0."CANCELED" IS NULL)
    GROUP BY T4."TrnspName"
    ORDER BY order_count DESC
''')
shipping_methods = cursor.fetchall()

print("SHIPPING METHODS FOR ACTIVE OPEN ORDERS:")
for method in shipping_methods:
    name = method[0] if method[0] is not None else "BLANK / NONE"
    count = method[1]
    print(f"  - {name}: {count} orders")
