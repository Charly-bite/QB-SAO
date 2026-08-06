"""
Unit tests for P1-01 Shared DatabaseClient Singleton (Connection Pool Consolidation)
"""

import pytest
from app import create_app
from core.database_client import DatabaseClient


def test_app_shares_single_database_client_instance(app):
    """Verify that all domain managers share the app-level db_client singleton instance."""
    db_client = getattr(app, "db_client", None)
    assert db_client is not None, "app.db_client singleton must be initialized in create_app()"

    assert app.user_manager.db_client is db_client, "UserManager must use app.db_client"
    assert app.order_status_mgr.db_client is db_client, "OrderStatusManager must use app.db_client"
    assert app.factura_metadata_mgr.db_client is db_client, "FacturaMetadataManager must use app.db_client"
    assert app.relacion_mgr.db_client is db_client, "RelacionManager must use app.db_client"
    assert app.audit_mgr.db_client is db_client, "AuditManager must use app.db_client"


def test_managers_fallback_to_independent_db_client_when_not_passed():
    """Verify that managers instantiate their own DatabaseClient when db_client is not provided (standalone usage)."""
    from core.audit_manager import AuditManager
    mgr = AuditManager()
    assert mgr.db_client is not None
    assert isinstance(mgr.db_client, DatabaseClient)
