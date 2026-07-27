"""
Unit tests for P2-01 Write Queue Non-Blocking Timeout
"""

import queue
import sys
import time
from unittest.mock import MagicMock, patch
import pytest
from core.factura_metadata_manager import FacturaMetadataManager


def test_enqueue_write_handles_queue_full_gracefully(tmp_path):
    """Verify that _enqueue_write does not hang or raise exception when queue is full."""
    db_file = str(tmp_path / "metadata.json")
    mgr = FacturaMetadataManager(db_path=db_file)

    # Replace write_queue with a tiny maxsize=1 queue
    test_queue = queue.Queue(maxsize=1)
    test_queue.put(("item1.json", {"key": "val1"}))  # fill queue
    mgr._write_queue = test_queue

    with patch.dict(sys.modules):
        sys.modules.pop("pytest", None)
        with patch("core.factura_metadata_manager.logger") as mock_logger:
            start_time = time.time()
            with patch.object(test_queue, "put", side_effect=queue.Full):
                mgr._enqueue_write("item2.json", {"key": "val2"})
            duration = time.time() - start_time

            # Should complete quickly without throwing queue.Full exception to caller
            assert duration < 1.0
            mock_logger.warning.assert_called_once()
            call_msg = mock_logger.warning.call_args[0][0]
            assert "JSON write queue full" in call_msg
