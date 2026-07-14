import sys
import os
import json
from collections import defaultdict

# Add parent directory to path so we can import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database_client import DatabaseClient
from sqlalchemy import text

EXPECTED_FLOW = [
    "Pendiente",
    "En Proceso",
    "Entregado",
    "Facturacion",
    "Relacion de envio",
    "Enviado al cliente"
]

SIDE_STATES = ["Cancelado", "En Espera"]

def audit_triggers():
    client = DatabaseClient()
    if not client.connect() or not client.engine:
        print("Error: Could not connect to database.")
        return

    print("Fetching audit logs for order status changes...")
    
    # Query all status updates
    query = text("""
        SELECT entity_id as order_id, timestamp, username, details
        FROM audit_logs
        WHERE action_type = 'UPDATE_ORDER_STATUS'
        ORDER BY entity_id, timestamp ASC
    """)

    order_history = defaultdict(list)
    
    with client.engine.connect() as conn:
        result = conn.execute(query)
        for row in result:
            try:
                details = json.loads(row.details) if row.details else {}
                status = details.get("new_status")
                if status:
                    order_history[row.order_id].append({
                        "timestamp": row.timestamp,
                        "status": status,
                        "username": row.username
                    })
            except Exception as e:
                pass

    anomalies = []
    
    for order_id, history in order_history.items():
        current_index = -1
        
        for i, event in enumerate(history):
            status = event["status"]
            
            if status in SIDE_STATES:
                continue
                
            try:
                new_index = EXPECTED_FLOW.index(status)
            except ValueError:
                anomalies.append({
                    "order_id": order_id,
                    "issue": f"Unknown status '{status}'",
                    "event": event,
                    "history": [e["status"] for e in history]
                })
                continue
                
            if current_index == -1:
                # First event in history (could be partial history if older logs were cleaned up)
                current_index = new_index
            else:
                if new_index < current_index:
                    anomalies.append({
                        "order_id": order_id,
                        "issue": f"Retrocedió de {EXPECTED_FLOW[current_index]} a {status}",
                        "event": event,
                        "history": [e["status"] for e in history]
                    })
                elif new_index > current_index + 1:
                    skipped = EXPECTED_FLOW[current_index + 1 : new_index]
                    anomalies.append({
                        "order_id": order_id,
                        "issue": f"Saltó pasos: {', '.join(skipped)} (brincó de {EXPECTED_FLOW[current_index]} a {status})",
                        "event": event,
                        "history": [e["status"] for e in history]
                    })
                
                current_index = new_index

    print(f"Auditoría completada. {len(order_history)} pedidos revisados.")
    print(f"Se encontraron {len(anomalies)} anomalías.\n")
    print("=" * 60)
    
    for a in anomalies:
        print(f"Anomalía en el Pedido #{a['order_id']}: {a['issue']}")
        print(f"  Usuario responsable : {a['event']['username']}")
        print(f"  Fecha y hora        : {a['event']['timestamp']}")
        print(f"  Historial completo  : {' -> '.join(a['history'])}")
        print("-" * 60)

if __name__ == "__main__":
    audit_triggers()
