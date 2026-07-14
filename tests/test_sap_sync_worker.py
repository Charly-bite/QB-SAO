import pytest
from unittest.mock import MagicMock, patch
from core.sap_sync_worker import SAPSyncWorker

class DummyApp:
    def __init__(self):
        self.sap_available = True
        self.sap_connector = MagicMock()
        self.sap_connector.connected = True
        self.order_status_mgr = MagicMock()
        self.order_status_mgr.reconcile_statuses.return_value = []
        
    def app_context(self):
        class Context:
            def __enter__(self): pass
            def __exit__(self, exc_type, exc_val, exc_tb): pass
        return Context()

@pytest.fixture
def mock_app():
    return DummyApp()

def test_sync_sap_sap_unavailable(mock_app):
    mock_app.sap_available = False
    worker = SAPSyncWorker(mock_app)
    worker.sync_sap()
    # It should exit immediately
    mock_app.sap_connector.get_recent_orders.assert_not_called()

@patch('routes.orders._check_delivery_and_invoice')
@patch('routes.orders._publish_event')
def test_sync_sap_success(mock_publish, mock_check, mock_app):
    mock_app.sap_connector.get_recent_orders.return_value = [{"order_id": "123", "status": "Pending"}]
    mock_app.order_status_mgr.reconcile_statuses.return_value = [
        {"order_id": "123", "customer": "Test", "from": "Pending", "to": "En proceso"}
    ]
    
    worker = SAPSyncWorker(mock_app)
    worker.sync_sap()
    
    # Assertions
    mock_app.sap_connector.get_recent_orders.assert_called_once_with(limit=50)
    mock_app.order_status_mgr.bulk_import_from_sap.assert_called_once_with([{"order_id": "123", "status": "Pending"}])
    mock_check.assert_called_once_with(mock_app.sap_connector, mock_app.order_status_mgr, [{"order_id": "123", "status": "Pending"}])
    
    # Check that events were published
    assert mock_publish.call_count == 2
    mock_publish.assert_any_call({"type": "sync_completed"})
    
@patch('routes.orders._check_delivery_and_invoice')
@patch('routes.orders._publish_event')
def test_sync_sap_handles_sap_exception(mock_publish, mock_check, mock_app):
    mock_app.sap_connector.get_recent_orders.side_effect = Exception("SAP error")
    
    worker = SAPSyncWorker(mock_app)
    worker.sync_sap()
    
    # Ensure it didn't crash and passed empty list to _check_delivery_and_invoice
    mock_check.assert_called_once_with(mock_app.sap_connector, mock_app.order_status_mgr, [])

def test_run_loop(mock_app):
    worker = SAPSyncWorker(mock_app)
    worker.interval_seconds = 0.01  # very short wait
    worker.sync_sap = MagicMock()
    
    # Mock the wait so it doesn't actually sleep 5 seconds initially
    original_wait = worker._stop_event.wait
    def fast_wait(timeout):
        return original_wait(0.01)
    worker._stop_event.wait = fast_wait
    
    # Start thread
    worker.start()
    
    # Wait briefly for thread to loop
    import time
    time.sleep(0.05)
    
    # Stop thread
    worker.stop()
    worker.join(timeout=1.0)
    
    # Ensure sync_sap was called at least once
    assert worker.sync_sap.call_count >= 1
    assert not worker.is_alive()
