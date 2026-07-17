import threading
import time
import logging

logger = logging.getLogger(__name__)

class SAPSyncWorker(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self._stop_event = threading.Event()
        self.interval_seconds = 60

    def run(self):
        logger.info("SAP Sync Worker thread started.")
        # Wait a bit before first run to let the server start up
        self._stop_event.wait(5.0)
        
        while not self._stop_event.is_set():
            try:
                self.sync_sap()
            except Exception as e:  # pragma: no cover
                logger.error(f"Error in SAP sync worker: {e}")
            
            # Wait for next interval or stop event
            self._stop_event.wait(self.interval_seconds)
            
    def stop(self):
        self._stop_event.set()

    def sync_sap(self):
        with self.app.app_context():
            if not self.app.sap_available:
                return

            order_mgr = self.app.order_status_mgr
            sap = self.app.sap_connector
            if not sap:  # pragma: no cover
                from core.sap_connector import SAPHanaConnector
                try:
                    sap_user = os.environ.get("SAP_USER")
                    sap_pass = os.environ.get("SAP_PASS")
                    sap = SAPHanaConnector(
                        host=os.environ.get("SAP_HOST", ""),
                        port=int(os.environ.get("SAP_PORT", 30015)),
                        username=sap_user,
                        password=sap_pass,
                        schema=os.environ.get("SAP_SCHEMA", ""),
                    )
                    self.app.sap_connector = sap
                except Exception as e:
                    logger.warning(f"Worker could not initialize SAPHanaConnector: {e}")
                    return

            if not sap.connected:  # pragma: no cover
                if not sap.connect():
                    logger.warning("Worker could not connect to SAP.")
                    return

            # Import new orders
            try:
                recent_orders = sap.get_recent_orders(limit=50)
                if recent_orders:
                    order_mgr.bulk_import_from_sap(recent_orders)
            except Exception as e:
                logger.error(f"Failed to fetch recent orders: {e}")
                recent_orders = []

            # Check invoices and deliveries (re-using the logic from routes/orders.py)
            from routes.orders import _check_delivery_and_invoice, _publish_event
            _check_delivery_and_invoice(sap, order_mgr, recent_orders)

            # Reconcile statuses and get changes
            changes = order_mgr.reconcile_statuses()

            # Emit specific status change events for global notifications
            for c in changes:
                _publish_event({
                    "type": "status_changed",
                    "order_id": c["order_id"],
                    "customer": c["customer"],
                    "from": c["from"],
                    "to": c["to"]
                })

            # Notify clients to refresh their tables
            _publish_event({"type": "sync_completed"})
