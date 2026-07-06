import json
import os
import sys

def main():
    sga_history_path = r"C:\Users\QB_DESARROLLO\Desktop\SGA PROD\sga_web\history.json"
    sao_db_path = r"C:\Users\QB_DESARROLLO\SAO PROD\data\order_status_db.json"
    
    # 1. Load SGA History
    print("Loading SGA History from JSON...")
    printed_orders = {}
    if os.path.exists(sga_history_path):
        try:
            with open(sga_history_path, "r", encoding="latin-1") as f:
                history = json.load(f)
        except Exception as e:
            print(f"Error loading SGA history: {e}")
            history = []
                
        for entry in history:
            if entry.get("event_type") == "DIRECT_PRINT_JOB":
                details = entry.get("details", {})
                order_id = str(details.get("order", details.get("order_id", "")))
                if order_id:
                    printed_orders[order_id] = entry
    
    print(f"Found {len(printed_orders)} unique printed orders in SGA history.")
    
    # 2. Load SAO Orders
    print("Loading SAO Orders from JSON...")
    sao_orders = {}
    if os.path.exists(sao_db_path):
        with open(sao_db_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                sao_orders = data.get("orders", {})
            except Exception as e:
                print(f"Error loading SAO db: {e}")
                
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
            status = sao_orders[order_id].get("status")
            if status not in processed_statuses:
                not_updated_in_sao.append((order_id, status))
                
    # Force UTF-8 stdout
    sys.stdout.reconfigure(encoding='utf-8')
    
    print("\n" + "="*50)
    print("AUDIT RESULTS: SGA Printed vs SAO Status")
    print("="*50)
    
    print(f"\nOrders missing in SAO tracking completely: {len(missing_in_sao)}")
    if missing_in_sao:
        print("  Missing orders:", ", ".join(missing_in_sao[:20]))
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
