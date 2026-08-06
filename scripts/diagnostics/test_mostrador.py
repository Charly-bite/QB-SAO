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

# 1. Total orders today
cursor.execute(f'SELECT COUNT(*) FROM {schema}."ORDR" WHERE "DocDate" = CURRENT_DATE')
total_today = cursor.fetchone()[0]

# 2. Orders with MOSTRADOR in shipping method today
cursor.execute(f'''
    SELECT T0."DocNum", T0."CardName", T4."TrnspName" 
    FROM {schema}."ORDR" T0 
    LEFT JOIN {schema}."OSHP" T4 ON T0."TrnspCode" = T4."TrnspCode" 
    WHERE T0."DocDate" = CURRENT_DATE 
    AND T4."TrnspName" LIKE '%MOSTRADOR%'
''')
shipping_mostrador = cursor.fetchall()

# 3. Orders with MOSTRADOR in customer name today
cursor.execute(f'''
    SELECT T0."DocNum", T0."CardName", T4."TrnspName" 
    FROM {schema}."ORDR" T0 
    LEFT JOIN {schema}."OSHP" T4 ON T0."TrnspCode" = T4."TrnspCode" 
    WHERE T0."DocDate" = CURRENT_DATE 
    AND T0."CardName" LIKE '%MOSTRADOR%'
''')
name_mostrador = cursor.fetchall()

print(f"TOTAL ORDERS TODAY: {total_today}")
print(f"ORDERS WITH MOSTRADOR IN SHIPPING: {len(shipping_mostrador)}")
for o in shipping_mostrador:
    print(f"  - {o[0]}: {o[1]} (Shipping: {o[2]})")

print(f"\nORDERS WITH MOSTRADOR IN NAME: {len(name_mostrador)}")
for o in name_mostrador:
    print(f"  - {o[0]}: {o[1]} (Shipping: {o[2]})")
