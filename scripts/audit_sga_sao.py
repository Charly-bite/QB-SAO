import sys
import os

# Ensure we can import from SAO core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.order_status_manager import OrderStatusManager

# Also import from SGA history
sys.path.insert(0, r"C:\Users\QB_DESARROLLO\Desktop\SGA PROD\sga_web\core")
from history_manager import HistoryManager

def main():
    print("Loading SGA History...")
    history_mgr = HistoryManager()
    sga_history = history_mgr.get_history()
    
    print("Loading SAO Orders...")
    sao_mgr = OrderStatusManager()
    sao_orders = sao_mgr.get_all_orders()
    
    # Identify orders printed in SGA
    printed_orders = {}
    for entry in sga_history:
        if entry.get("event_type") == "DIRECT_PRINT_JOB":
            details = entry.get("details", {})
            order_id = details.get("order_id")
            if order_id:
                printed_orders[str(order_id)] = entry
                
    # Create a map of SAO orders
    sao_order_map = {str(o.get("order_id")): o for o in sao_orders}
    
    # Statuses that indicate the label was processed
    processed_statuses = [
        "En Proceso", 
        "Entregado", 
        "Facturacion", 
        "Relacion de envio", 
        "Enviado al cliente"
    ]
    
    print("\n--- Audit Results ---")
    missing_in_sao = []
    not_updated_in_sao = []
    
    for order_id, sga_entry in printed_orders.items():
        sao_order = sao_order_map.get(order_id)
        if not sao_order:
            missing_in_sao.append(order_id)
        else:
            status = sao_order.get("status")
            if status not in processed_statuses:
                not_updated_in_sao.append((order_id, status))
                
    print(f"Total Unique Orders Printed in SGA: {len(printed_orders)}")
    print(f"Total Orders Missing in SAO (Not Loaded): {len(missing_in_sao)}")
    if missing_in_sao:
        print(f" -> Missing Orders: {missing_in_sao}")
        
    print(f"Total Orders in SAO but Not Updated (Still Pendiente, etc.): {len(not_updated_in_sao)}")
    if not_updated_in_sao:
        print(f" -> Not Updated: {not_updated_in_sao}")
        
if __name__ == "__main__":
    main()
