import os
import time
import socket

_sga_cache = {"status": True, "timestamp": 0}

def check_sga_status(timeout=0.5, cache_ttl=10, max_attempts=3, retry_delay=0.1):
    """
    Checks if the SGA system (database or web server) is online.
    Caches the result to avoid blocking the main thread.
    Tries up to max_attempts with a short delay to handle transient glitches.
    """
    now = time.time()
    if now - _sga_cache["timestamp"] < cache_ttl:
        return _sga_cache["status"]

    sga = False
    sql_server = os.environ.get("SQL_SERVER", "192.168.2.237")
    sga_web = os.environ.get("SGA_WEB_HOST", "192.168.2.134")
    
    for attempt in range(1, max_attempts + 1):
        # Fast check: ping SQL Server (1433) or Web (5000)
        try:
            with socket.create_connection((sql_server, 1433), timeout=timeout):
                sga = True
                break
        except Exception:
            try:
                with socket.create_connection((sga_web, 5000), timeout=timeout):  # pragma: no cover
                    sga = True  # pragma: no cover
                    break
            except Exception:
                pass
        
        if attempt < max_attempts:
            time.sleep(retry_delay)

    _sga_cache["status"] = sga
    _sga_cache["timestamp"] = now
    return sga
