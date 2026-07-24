"""
Tests for _SSERegistry (P0-01 SSE Thread Starvation & Connection Registry)
"""

import queue
import threading
import time
import pytest
from routes.orders import _SSERegistry, _SSE_PER_USER_LIMIT, _SSE_GLOBAL_LIMIT, _sse_registry


@pytest.fixture
def registry():
    """Returns a fresh instance of _SSERegistry for isolated testing."""
    return _SSERegistry()


class TestSSERegistry:
    """Test suite for _SSERegistry class methods, eviction policies, and thread safety."""

    def test_add_single_subscriber(self, registry):
        q = queue.Queue()
        registry.add(q, username="UserA")
        assert registry.count() == 1
        assert registry.count_by_user() == {"UserA": 1}
        assert q in registry.queues()

    def test_remove_subscriber(self, registry):
        q1 = queue.Queue()
        q2 = queue.Queue()
        registry.add(q1, username="UserA")
        registry.add(q2, username="UserA")
        assert registry.count() == 2

        registry.remove(q1)
        assert registry.count() == 1
        assert registry.queues() == [q2]
        assert registry.count_by_user() == {"UserA": 1}

    def test_per_user_limit_eviction(self, registry):
        queues = [queue.Queue() for _ in range(_SSE_PER_USER_LIMIT + 1)]
        
        # Add max allowed
        for i in range(_SSE_PER_USER_LIMIT):
            registry.add(queues[i], username="UserLimit")
            time.sleep(0.01)

        assert registry.count() == _SSE_PER_USER_LIMIT
        assert registry.count_by_user()["UserLimit"] == _SSE_PER_USER_LIMIT

        # Add one more (exceeding limit)
        registry.add(queues[_SSE_PER_USER_LIMIT], username="UserLimit")

        # The first (oldest) queue should have received None poison pill
        assert queues[0].get_nowait() is None
        assert registry.count() == _SSE_PER_USER_LIMIT
        assert queues[0] not in registry.queues()
        assert queues[_SSE_PER_USER_LIMIT] in registry.queues()

    def test_global_limit_eviction(self, monkeypatch, registry):
        monkeypatch.setattr("routes.orders._SSE_GLOBAL_LIMIT", 5)
        queues = [queue.Queue() for _ in range(6)]

        for i in range(5):
            registry.add(queues[i], username=f"User_{i}")
            time.sleep(0.005)

        assert registry.count() == 5

        # Add 6th subscriber to trigger global eviction
        registry.add(queues[5], username="User_5")

        assert queues[0].get_nowait() is None
        assert registry.count() == 5
        assert queues[0] not in registry.queues()

    def test_queues_snapshot(self, registry):
        q1 = queue.Queue()
        q2 = queue.Queue()
        registry.add(q1, username="UserA")
        registry.add(q2, username="UserB")

        snapshot = registry.queues()
        assert snapshot == [q1, q2]
        # Modifying snapshot does not alter internal subscribers
        snapshot.clear()
        assert registry.count() == 2

    def test_count_and_count_by_user(self, registry):
        q1 = queue.Queue()
        q2 = queue.Queue()
        q3 = queue.Queue()

        registry.add(q1, username="UserA")
        registry.add(q2, username="UserA")
        registry.add(q3, username="UserB")

        assert registry.count() == 3
        assert registry.count_by_user() == {"UserA": 2, "UserB": 1}

    def test_thread_safety(self, registry):
        threads = []
        errors = []

        def worker(user_idx):
            try:
                for _ in range(20):
                    q = queue.Queue()
                    registry.add(q, username=f"Worker_{user_idx}")
                    time.sleep(0.001)
                    registry.remove(q)
            except Exception as e:
                errors.append(e)

        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_poison_pill_signal(self, registry):
        q = queue.Queue()
        registry.add(q, username="PillUser")
        
        # Manually trigger eviction
        q_extra = queue.Queue()
        for _ in range(_SSE_PER_USER_LIMIT):
            registry.add(queue.Queue(), username="PillUser")

        # The original q should be evicted with poison pill None
        assert q.get(timeout=1.0) is None

    def test_multiple_users_isolation(self, registry):
        q_a1 = queue.Queue()
        q_a2 = queue.Queue()
        q_b1 = queue.Queue()

        registry.add(q_a1, username="UserA")
        registry.add(q_a2, username="UserA")
        registry.add(q_b1, username="UserB")

        assert registry.count_by_user() == {"UserA": 2, "UserB": 1}
        registry.remove(q_a1)
        assert registry.count_by_user() == {"UserA": 1, "UserB": 1}
        assert q_b1 in registry.queues()


class TestSSEHealthEndpoint:
    """Test health detailed endpoint SSE metrics reporting."""

    def test_health_detailed_endpoint_metrics(self, client):
        response = client.get("/api/health/detailed")
        assert response.status_code in (200, 503)
        data = response.get_json()
        assert "sse_connections" in data
        assert "sse_connections_by_user" in data
