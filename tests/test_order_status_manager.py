"""
Unit tests for OrderStatusManager — pure business logic.
These tests use JSON-only mode (no SQL Server).
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock


def _make_mock_db_client():
    """Return a mock DatabaseClient class that never connects."""
    mock_cls = MagicMock()
    inst = MagicMock()
    inst.connect.return_value = False
    inst.get_sql_engine.return_value = None
    mock_cls.return_value = inst
    return mock_cls


@pytest.fixture()
def osm():
    """Create an OrderStatusManager backed by a temporary JSON file."""
    tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
    seed = {
        "orders": {
            "5001": {
                "order_id": "5001",
                "customer_code": "C100",
                "customer_name": "Unit Test Client",
                "order_date": "2026-02-01",
                "delivery_date": "2026-02-05",
                "total": 1000,
                "currency": "MXN",
                "comments": "",
                "items": [],
                "sap_status": "Abierto",
                "status": "Pendiente",
                "status_history": [
                    {"status": "Pendiente", "timestamp": "2026-02-01T00:00:00", "user": "system", "notes": "seed"}
                ],
                "imported_at": "2026-02-01T00:00:00",
                "last_updated": "2026-02-01T00:00:00",
                "updated_by": "system",
                "created_by": "system"
            }
        }
    }
    json.dump(seed, tmp, ensure_ascii=False)
    tmp.close()

    mock_cls = _make_mock_db_client()
    with patch('core.database_client.DatabaseClient', mock_cls):
        from core.order_status_manager import OrderStatusManager
        mgr = OrderStatusManager(db_path=tmp.name)

    yield mgr

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


class TestOrderRetrieval:

    def test_get_existing_order(self, osm):
        order = osm.get_order('5001')
        assert order is not None
        assert order['customer_name'] == 'Unit Test Client'

    def test_get_missing_order_returns_none(self, osm):
        assert osm.get_order('99999') is None

    def test_get_all_orders(self, osm):
        orders = osm.get_all_orders()
        assert len(orders) >= 1

    def test_get_orders_by_status(self, osm):
        pending = osm.get_orders_by_status('Pendiente')
        assert any(o['order_id'] == '5001' for o in pending)

    def test_get_active_orders(self, osm):
        active = osm.get_active_orders()
        ids = [o['order_id'] for o in active]
        assert '5001' in ids


class TestStatusTransitions:

    def test_update_status_success(self, osm):
        result = osm.update_status('5001', 'En Proceso', 'testuser', 'Starting')
        assert result is not None
        assert osm.get_order('5001')['status'] == 'En Proceso'

    def test_update_status_appends_history(self, osm):
        osm.update_status('5001', 'Entregado', 'operator1', 'Picking')
        history = osm.get_order('5001')['status_history']
        last = history[-1]
        assert last['status'] == 'Entregado'
        assert last['user'] == 'operator1'
        assert last['previous_status'] == 'Pendiente'

    def test_update_status_missing_order(self, osm):
        result = osm.update_status('99999', 'Pendiente', 'user', '')
        assert result is False

    def test_full_lifecycle(self, osm):
        """Walk an order through the full lifecycle."""
        steps = ['En Proceso', 'Entregado', 'Facturacion',
                 'Relacion de envio', 'Enviado al cliente']
        for step in steps:
            osm.update_status('5001', step, 'admin', f'Moving to {step}')

        order = osm.get_order('5001')
        assert order['status'] == 'Enviado al cliente'
        assert len(order['status_history']) == 1 + len(steps)  # seed + transitions


class TestStatusCounts:

    def test_count_by_status(self, osm):
        counts = osm.get_order_count_by_status()
        assert counts['Pendiente'] == 1
        assert counts.get('Cancelado', 0) == 0

    def test_status_options(self, osm):
        options = osm.get_status_options()
        assert 'Pendiente' in options
        assert 'Cancelado' in options


class TestImportFromSAP:

    def test_import_new_order(self, osm):
        sap_data = {
            'DocNum': '6001',
            'CardCode': 'C200',
            'CardName': 'SAP Import Client',
            'DocDate': '2026-03-01',
            'DocDueDate': '2026-03-05',
            'DocTotal': 7500,
            'DocCurrency': 'USD',
            'items': [{'ItemCode': 'X1', 'Quantity': 5}],
            'sap_status': 'Abierto',
        }
        result = osm.import_from_sap(sap_data, imported_by='test_sync')
        assert result['order_id'] == '6001'
        assert result['status'] == 'Pendiente'
        assert result['customer_name'] == 'SAP Import Client'

    def test_reimport_preserves_local_status(self, osm):
        """If we re-import an existing order, the local status should NOT reset."""
        osm.update_status('5001', 'Entregado', 'admin', 'Advanced')

        sap_data = {
            'DocNum': '5001',
            'CardCode': 'C100',
            'CardName': 'Unit Test Client Updated',
            'DocDate': '2026-02-01',
        }
        result = osm.import_from_sap(sap_data)
        assert result['status'] == 'Entregado'  # preserved


class TestStatusNormalization:

    def test_legacy_label_migration(self, osm):
        """Legacy labels should be normalized on load."""
        osm.orders['7001'] = {
            'order_id': '7001',
            'status': 'Listo para Envío',
            'status_history': [
                {'status': 'Enviado', 'timestamp': '2026-01-01T00:00:00'}
            ]
        }
        osm._normalize_status_labels()
        assert osm.orders['7001']['status'] == 'Relacion de envio'
        assert osm.orders['7001']['status_history'][0]['status'] == 'Enviado al cliente'


class TestDeleteOrder:

    def test_delete_existing(self, osm):
        osm.delete_order('5001')
        assert osm.get_order('5001') is None

    def test_delete_missing(self, osm):
        result = osm.delete_order('99999')
        assert result is False


class TestExportForWeb:

    def test_export_structure(self, osm):
        data = osm.export_for_web()
        assert 'orders' in data
        assert 'status_counts' in data
        assert 'generated_at' in data
        assert len(data['orders']) >= 1
