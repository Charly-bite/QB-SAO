"""
Request logger middleware tests — verify logging and skip behaviour.
"""
import logging


class TestRequestLoggerMiddleware:
    """Verify the request logger hooks log/skip correctly."""

    def test_health_request_is_logged(self, client, caplog):
        """Non-static endpoints should be logged."""
        with caplog.at_level(logging.DEBUG, logger='open_oms.requests'):
            client.get('/health')
        # The after_request hook should have produced a log entry for /health
        assert any('/health' in record.message for record in caplog.records)

    def test_static_request_is_skipped(self, client, caplog):
        """Requests starting with /static/ should NOT be logged."""
        with caplog.at_level(logging.DEBUG, logger='open_oms.requests'):
            client.get('/static/css/tailwind.css')
        assert not any('/static/' in record.message for record in caplog.records)

    def test_favicon_request_is_skipped(self, client, caplog):
        """Requests to /favicon.ico should NOT be logged."""
        with caplog.at_level(logging.DEBUG, logger='open_oms.requests'):
            client.get('/favicon.ico')
        assert not any('/favicon.ico' in record.message for record in caplog.records)

    def test_logged_entry_contains_method_and_status(self, client, caplog):
        """Log entries should contain the HTTP method and status code."""
        with caplog.at_level(logging.DEBUG, logger='open_oms.requests'):
            client.get('/health')
        health_logs = [r.message for r in caplog.records if '/health' in r.message]
        assert len(health_logs) >= 1
        assert 'GET' in health_logs[0]
        assert '200' in health_logs[0]
