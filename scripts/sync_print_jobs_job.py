"""Background job: map SGA print jobs to orders and auto-update status.

Run as:
    python scripts/sync_print_jobs_job.py
"""

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pyodbc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["WERKZEUG_RUN_MAIN"] = "true"

from app import create_app
from core.order_status_manager import OrderStatus
from core.print_event_matcher import extract_print_items, find_matching_order_ids

EVENT_TYPES = ("DIRECT_PRINT_JOB", "PRINT_JOB", "PRINT_JOB_HTML")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = _PROJECT_ROOT / "logs" / "print_sync_state.json"
UNRESOLVED_FILE = _PROJECT_ROOT / "logs" / "print_sync_unresolved.jsonl"


def _sql_connection_string() -> str:
    host = os.environ.get("SQL_SERVER", "192.168.2.237")
    db = os.environ.get("SQL_DATABASE", "SGA_Database")
    user = os.environ.get("SQL_USER", "")
    password = os.environ.get("SQL_PASSWORD", "")

    if not user or not password:
        raise RuntimeError("Missing SQL_USER/SQL_PASSWORD environment variables")

    # Prefer modern driver, fallback to legacy if needed.
    drivers = pyodbc.drivers()
    driver = "ODBC Driver 17 for SQL Server" if "ODBC Driver 17 for SQL Server" in drivers else "SQL Server"

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={host};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        "Connection Timeout=5"
    )


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"last_id": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_id": None}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_unresolved(entry: Dict[str, Any]) -> None:
    UNRESOLVED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with UNRESOLVED_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _fetch_new_print_events(last_id: int) -> List[Dict[str, Any]]:
    conn = pyodbc.connect(_sql_connection_string())
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(EVENT_TYPES))
    sql = (
        "SELECT id, [timestamp], event_type, username, details "
        "FROM dbo.history_logs "
        f"WHERE id > ? AND event_type IN ({placeholders}) "
        "ORDER BY id ASC"
    )
    params = [last_id, *EVENT_TYPES]
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    events: List[Dict[str, Any]] = []
    for r in rows:
        events.append(
            {
                "id": int(r[0]),
                "timestamp": str(r[1]),
                "event_type": str(r[2]),
                "username": str(r[3]) if r[3] is not None else "sga",
                "details": str(r[4]) if r[4] is not None else "{}",
            }
        )
    return events


def _get_latest_print_event_id() -> int:
    conn = pyodbc.connect(_sql_connection_string())
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(EVENT_TYPES))
    sql = f"SELECT ISNULL(MAX(id), 0) FROM dbo.history_logs WHERE event_type IN ({placeholders})"
    cur.execute(sql, list(EVENT_TYPES))
    max_id = int(cur.fetchone()[0] or 0)
    conn.close()
    return max_id


def run_print_sync() -> None:
    app = create_app()
    with app.app_context():
        state = _load_state()
        raw_last_id = state.get("last_id", None)

        # Safety default: on first run, start from current latest event id.
        # This avoids processing months of historical print jobs unintentionally.
        if raw_last_id is None:
            try:
                bootstrap_id = _get_latest_print_event_id()
                _save_state(
                    {
                        "last_id": bootstrap_id,
                        "updated_at": datetime.datetime.now().isoformat(),
                        "bootstrapped": True,
                    }
                )
                print(
                    f"Bootstrap complete: last_id initialized to {bootstrap_id}. "
                    "Run again to process only new print events."
                )
                return
            except Exception as e:
                print(f"Failed to bootstrap print sync state: {e}")
                return

        last_id = int(raw_last_id)

        print(f"[{datetime.datetime.now().isoformat()}] Starting print sync (last_id={last_id})")

        try:
            events = _fetch_new_print_events(last_id)
        except Exception as e:
            print(f"Failed to fetch print events: {e}")
            return

        if not events:
            print("No new print events.")
            return

        order_mgr = app.order_status_mgr
        updated = 0
        unresolved = 0
        skipped = 0
        newest_id = last_id

        for event in events:
            newest_id = max(newest_id, event["id"])
            print_items = extract_print_items(event.get("details", "{}"))

            if not print_items:
                skipped += 1
                _append_unresolved(
                    {
                        "reason": "empty_or_invalid_items",
                        "event": event,
                    }
                )
                continue

            matches = find_matching_order_ids(print_items, order_mgr.get_all_orders())

            if len(matches) == 1:
                order_id = matches[0]
                order = order_mgr.get_order(order_id) or {}
                if order.get("status") == OrderStatus.IN_PROGRESS.value:
                    skipped += 1
                    continue

                ok = order_mgr.update_status(
                    order_id,
                    OrderStatus.IN_PROGRESS.value,
                    event.get("username", "sga"),
                    notes=(
                        f"Auto-actualizado por impresión SGA "
                        f"(event_id={event['id']}, type={event['event_type']}, items={sorted(print_items)})"
                    ),
                )
                if ok:
                    updated += 1
                else:
                    unresolved += 1
                    _append_unresolved(
                        {
                            "reason": "update_failed",
                            "event": event,
                            "matches": matches,
                        }
                    )
            else:
                unresolved += 1
                _append_unresolved(
                    {
                        "reason": "ambiguous_or_no_match",
                        "event": event,
                        "matches": matches,
                        "print_items": sorted(print_items),
                    }
                )

        _save_state({"last_id": newest_id, "updated_at": datetime.datetime.now().isoformat()})
        print(
            f"Print sync done: events={len(events)}, updated={updated}, unresolved={unresolved}, skipped={skipped}, last_id={newest_id}"
        )


if __name__ == "__main__":
    run_print_sync()
