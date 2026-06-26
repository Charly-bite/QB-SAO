from dotenv import load_dotenv
load_dotenv()
from core.sap_connector import SAPHanaConnector

sap = SAPHanaConnector()
sap.connect()
cur = sap._local.connection.cursor()
cur.execute(f'SELECT "DocNum", "DocEntry", "CANCELED", "DocStatus", "DocDate", "DocTotal" FROM {sap.schema}."OINV" WHERE "DocNum" IN (1000592, 17363, 17349)')
rows = cur.fetchall()
for r in rows:
    print(r)
