import pyodbc
import json
import collections

conn_str = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.2.237;DATABASE=SGA_Database;UID=sga_app_user;PWD=QuimicaBoss_2026!;TrustServerCertificate=yes"

def main():
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return

    # 1. Get printed labels from SGA history
    print("Fetching SGA Print Jobs...")
    cursor.execute("SELECT details FROM history_logs WHERE event_type = 'DIRECT_PRINT_JOB'")
    rows = cursor.fetchall()
    
    printed_orders = {}
    for row in rows:
        try:
            details = json.loads(row[0])
            order_id = str(details.get("order_id", ""))
            if order_id:
                printed_orders[order_id] = details
        except Exception:
            pass
            
    print(f"Found {len(printed_orders)} unique printed orders in SGA history.")

    # 2. Get SAO order statuses
    print("Fetching SAO Order Statuses...")
    cursor.execute("SELECT order_id, status FROM seguimiento_order_status")
    sao_rows = cursor.fetchall()
    sao_orders = {str(r[0]): r[1] for r in sao_rows}
    
    print(f"Found {len(sao_orders)} orders tracked in SAO.")

    # 3. Compare
    processed_statuses = [
        "En Proceso", 
        "Entregado", 
        "Facturacion", 
        "Relacion de envio", 
        "Enviado al cliente"
    ]
    
    missing_in_sao = []
    not_updated_in_sao = []
    
    for order_id in printed_orders:
        if order_id not in sao_orders:
            missing_in_sao.append(order_id)
        else:
            status = sao_orders[order_id]
            if status not in processed_statuses:
                not_updated_in_sao.append((order_id, status))
                
    # Format the output nicely
    print("\n" + "="*50)
    print("🎯 AUDIT RESULTS: SGA Printed vs SAO Status")
    print("="*50)
    
    print(f"\nOrders missing in SAO tracking completely: {len(missing_in_sao)}")
    if missing_in_sao:
        for o in missing_in_sao[:20]:
            print(f"  - Order #{o}")
        if len(missing_in_sao) > 20:
            print(f"  ... and {len(missing_in_sao)-20} more")
            
    print(f"\nOrders in SAO but still marked as Pendiente/Abierto (Not Updated): {len(not_updated_in_sao)}")
    if not_updated_in_sao:
        for o, s in not_updated_in_sao[:20]:
            print(f"  - Order #{o} (Status: {s})")
        if len(not_updated_in_sao) > 20:
            print(f"  ... and {len(not_updated_in_sao)-20} more")
            
    print("\n" + "="*50)

if __name__ == "__main__":
    main()
