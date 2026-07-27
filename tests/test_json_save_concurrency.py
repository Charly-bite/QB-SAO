"""
Unit tests for P1-03 JSON Save Deepcopy Concurrency Guard
"""

import threading
import time
import pytest


def test_save_database_deepcopy_concurrency_protection(app):
    """Verify that concurrent order dictionary mutations during _save_database do not raise RuntimeError."""
    osm = app.order_status_mgr
    errors = []
    stop_event = threading.Event()

    def mutator_thread(worker_id):
        idx = 0
        while not stop_event.is_set():
            try:
                order_key = f"CONC_{worker_id}_{idx}"
                osm.orders[order_key] = {
                    "order_id": order_key,
                    "status": "Pendiente",
                    "status_history": [{"status": "Pendiente", "timestamp": "2026-07-24T12:00:00"}],
                }
                idx += 1
                time.sleep(0.001)
            except Exception as e:
                errors.append(e)

    def saver_thread():
        for _ in range(15):
            try:
                osm._save_database(force=True)
                time.sleep(0.005)
            except Exception as e:
                errors.append(e)

    threads = []
    for i in range(5):
        t = threading.Thread(target=mutator_thread, args=(i,))
        threads.append(t)
        t.start()

    saver = threading.Thread(target=saver_thread)
    saver.start()
    saver.join()

    stop_event.set()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent mutation error caught during JSON save: {errors}"
