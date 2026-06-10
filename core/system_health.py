import os
import time
import socket

_sga_cache = {"status": True, "timestamp": 0}

def check_sga_status(timeout=0.5, cache_ttl=10):
    """
    Checks if the SGA system (database or web server) is online.
    Caches the result to avoid blocking the main thread.
    """
    global _sga_cache
    now = time.time()
    if now - _sga_cache["timestamp"] < cache_ttl:
        return _sga_cache["status"]

    sga = True
    sql_server = os.environ.get("SQL_SERVER", "192.168.2.237")
    sga_web = os.environ.get("SGA_WEB_HOST", "192.168.2.218")
    
    # Fast check: ping SQL Server (1433) or Web (5000)
    try:
        with socket.create_connection((sql_server, 1433), timeout=timeout):
            pass
    except Exception:
        try:
            with socket.create_connection((sga_web, 5000), timeout=timeout):
                pass
        except Exception:
            sga = False

    _sga_cache["status"] = sga
    _sga_cache["timestamp"] = now
    return sga
