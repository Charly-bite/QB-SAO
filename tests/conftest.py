"""
Test fixtures for Open-OMS.

All external dependencies (SAP HANA, SQL Server) are mocked so tests
run anywhere without infrastructure.
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Mock external drivers BEFORE any application import
# ---------------------------------------------------------------------------
# hdbcli is only available on machines with the SAP HANA client installed.
# We stub the entire package so `from core.sap_connector import ...` works.
_hdbcli_mock = MagicMock()
sys.modules.setdefault("hdbcli", _hdbcli_mock)
sys.modules.setdefault("hdbcli.dbapi", _hdbcli_mock.dbapi)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_database_client():
    """Return a mock DatabaseClient class whose instances never connect."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.connect.return_value = False
    mock_instance.get_sql_engine.return_value = None
    mock_cls.return_value = mock_instance
    return mock_cls


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _mock_database_client():
    """Session-scoped patch: prevent DatabaseClient from connecting to SQL Server.
    We patch at the SOURCE module so both local imports in user_manager and
    order_status_manager pick up the mock."""
    with (
        patch("core.database_client.pyodbc") as mock_pyodbc,
        patch("core.database_client.create_engine") as _mock_engine,
    ):
        mock_pyodbc.connect.side_effect = Exception("No SQL Server in tests")
        yield


@pytest.fixture()
def app(_mock_database_client):
    """Create a Flask application configured for testing."""
    # Use a temporary JSON file so tests don't touch the real DB
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    seed_data = {
        "orders": {
            "10001": {
                "order_id": "10001",
                "customer_code": "C001",
                "customer_name": "Cliente Prueba",
                "order_date": "2026-01-15",
                "delivery_date": "2026-01-20",
                "total": 5000.0,
                "currency": "MXN",
                "comments": "",
                "items": [
                    {"ItemCode": "PROD-A", "Dscription": "Producto A", "Quantity": 10}
                ],
                "sap_status": "Abierto",
                "status": "Pendiente",
                "status_history": [
                    {
                        "status": "Pendiente",
                        "timestamp": "2026-01-15T10:00:00",
                        "user": "system",
                        "notes": "Importado desde SAP",
                    }
                ],
                "imported_at": "2026-01-15T10:00:00",
                "last_updated": "2026-01-15T10:00:00",
                "updated_by": "system",
                "created_by": "system",
            },
            "10002": {
                "order_id": "10002",
                "customer_code": "C002",
                "customer_name": "Otro Cliente",
                "order_date": "2026-01-16",
                "delivery_date": "2026-01-22",
                "total": 12000.0,
                "currency": "MXN",
                "comments": "Urgente",
                "items": [],
                "sap_status": "Abierto",
                "status": "En Proceso",
                "status_history": [],
                "imported_at": "2026-01-16T08:00:00",
                "last_updated": "2026-01-16T09:00:00",
                "updated_by": "admin",
                "created_by": "admin",
            },
        },
        "last_updated": "2026-01-16T09:00:00",
    }
    json.dump(seed_data, tmp, ensure_ascii=False)
    tmp.close()

    # Patch DatabaseClient at the SOURCE module — both order_status_manager
    # and user_manager do `from core.database_client import DatabaseClient`
    # inside __init__, so patching the source module is the correct approach.
    mock_db_cls = _make_mock_database_client()

    with patch("core.database_client.DatabaseClient", mock_db_cls):
        from app import create_app

        test_app = create_app("testing")

        # Replace the order manager with one using our temp file
        from core.order_status_manager import OrderStatusManager

        test_app.order_status_mgr = OrderStatusManager(db_path=tmp.name)

    yield test_app

    # Cleanup temp file
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def runner(app):
    """Flask test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture()
def auth_client(app):
    """Authenticated test client (logged in as admin)."""
    client = app.test_client()
    with app.app_context():
        # Ensure admin user exists
        um = app.user_manager
        if "testadmin" not in um.users:
            um.create_user(
                username="testadmin",
                password="testpass123",
                full_name="Test Admin",
                role="admin",
            )
        # Log in
        client.post(
            "/login",
            data={
                "username": "testadmin",
                "password": "testpass123",
            },
            follow_redirects=True,
        )

    return client


@pytest.fixture()
def operator_client(app):
    """Authenticated test client with operator role."""
    client = app.test_client()
    with app.app_context():
        um = app.user_manager
        if "testoperator" not in um.users:
            um.create_user(
                username="testoperator",
                password="operpass123",
                full_name="Test Operator",
                role="operator",
            )
        client.post(
            "/login",
            data={
                "username": "testoperator",
                "password": "operpass123",
            },
            follow_redirects=True,
        )

    return client


@pytest.fixture()
def viewer_client(app):
    """Authenticated test client with viewer role (read-only)."""
    client = app.test_client()
    with app.app_context():
        um = app.user_manager
        if "testviewer" not in um.users:
            um.create_user(
                username="testviewer",
                password="viewpass123",
                full_name="Test Viewer",
                role="viewer",
            )
        client.post(
            "/login",
            data={
                "username": "testviewer",
                "password": "viewpass123",
            },
            follow_redirects=True,
        )

    return client


@pytest.fixture()
def seller_client(app):
    """Authenticated test client with seller role + SAP seller name."""
    client = app.test_client()
    with app.app_context():
        um = app.user_manager
        if "testseller" not in um.users:
            um.create_user(
                username="testseller",
                password="sellpass123",
                full_name="Test Seller",
                role="seller",
                sap_seller_name="system",  # Matches seed data created_by
            )
        client.post(
            "/login",
            data={
                "username": "testseller",
                "password": "sellpass123",
            },
            follow_redirects=True,
        )

    return client


@pytest.fixture()
def sell_manager_client(app):
    """Authenticated test client with sell_manager role."""
    client = app.test_client()
    with app.app_context():
        um = app.user_manager
        if "testmanager" not in um.users:
            um.create_user(
                username="testmanager",
                password="mgrpass123",
                full_name="Test Manager",
                role="sell_manager",
                sap_seller_name="MANAGER SAP",
            )
        client.post(
            "/login",
            data={
                "username": "testmanager",
                "password": "mgrpass123",
            },
            follow_redirects=True,
        )

    return client

