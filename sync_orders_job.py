"""
Background SAP Order Sync Job — Seguimiento Web
Run as: python sync_orders_job.py
Can be scheduled via Windows Task Scheduler.
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))

os.environ['WERKZEUG_RUN_MAIN'] = 'true'

from app import create_app
from core.order_status_manager import OrderStatus


def run_order_sync():
    app = create_app()
    with app.app_context():
        if not app.sap_available:
            print("SAP not available. Exiting.")
            return

        sap = app.sap_connector
        if not sap:
            print("SAP Connector not set up. Exiting.")
            return

        if not sap.connected:
            try:
                sap.connect()
            except Exception as e:
                print(f"Failed to connect to SAP: {e}")
                return

        order_mgr = app.order_status_mgr
        print(f"[{datetime.datetime.now().isoformat()}] Starting SAP order sync...")
        recent_orders = sap.get_recent_orders(limit=100, only_open=False)

        updated = 0
        new_orders = 0

        for order_data in recent_orders:
            if not order_data or 'header' not in order_data:
                continue
            header = order_data.get('header', {})
            items = order_data.get('items', [])
            sap_user = header.get('updater_name', header.get('creator_name', 'background_sync'))

            flattened = {
                'DocNum': header.get('order_number'),
                'CardCode': header.get('customer_code'),
                'CardName': header.get('customer_name'),
                'DocDate': header.get('order_date'),
                'DocDueDate': header.get('delivery_date'),
                'DocTotal': header.get('total_value', 0),
                'DocCurrency': header.get('currency', 'MXN'),
                'sap_status': header.get('sap_status', 'Abierto'),
                'factura_number': header.get('factura_number'),
                'items': items,
                'updated_by': sap_user,
            }

            oid = str(flattened['DocNum'])
            if oid in order_mgr.orders:
                cur_sap = order_mgr.orders[oid].get('sap_status')
                new_sap = flattened['sap_status']
                cur_fact = order_mgr.orders[oid].get('factura_number')
                new_fact = flattened.get('factura_number')

                needs_update = False

                if cur_sap != new_sap:
                    order_mgr.orders[oid]['sap_status'] = new_sap
                    cur_local = order_mgr.orders[oid].get('status')
                    if new_sap == 'Cerrado' and cur_local not in [
                        OrderStatus.INVOICING.value, OrderStatus.READY.value, OrderStatus.SHIPPED.value
                    ]:
                        order_mgr.orders[oid]['status'] = OrderStatus.INVOICING.value
                        order_mgr.orders[oid]['last_updated'] = datetime.datetime.now().isoformat()
                    elif new_sap == 'Cancelado' and cur_local != OrderStatus.CANCELLED.value:
                        order_mgr.orders[oid]['status'] = OrderStatus.CANCELLED.value
                        order_mgr.orders[oid]['last_updated'] = datetime.datetime.now().isoformat()
                    needs_update = True

                if new_fact and cur_fact != new_fact:
                    order_mgr.orders[oid]['factura_number'] = new_fact
                    needs_update = True

                if needs_update:
                    updated += 1
            else:
                order_mgr.import_from_sap(flattened, imported_by=sap_user)
                new_orders += 1

        if updated > 0 or new_orders > 0:
            order_mgr._save_database()
            print(f"✅ Sync: +{new_orders} new, {updated} updated")
        else:
            print("No updates needed.")


if __name__ == "__main__":
    run_order_sync()
