#!/usr/bin/env python3
import sys
import time
import subprocess
import argparse
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("open_oms.sync_daemon")
handler = logging.FileHandler(LOG_DIR / "print_sync_daemon.log")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def run_sync_once(sync_script_path: Path):
    logger.info("Running sync job: %s", sync_script_path)
    try:
        p = subprocess.run([sys.executable, str(sync_script_path)], cwd=str(sync_script_path.parent), capture_output=True, text=True)
        logger.info("sync exit=%s", p.returncode)
        if p.stdout:
            logger.info("stdout: %s", p.stdout.strip())
        if p.stderr:
            logger.error("stderr: %s", p.stderr.strip())
    except Exception as e:
        logger.exception("Exception while running sync job: %s", e)


def main(interval: int, once: bool):
    script_dir = Path(__file__).resolve().parent
    sync_script = script_dir / "sync_print_jobs_job.py"
    if not sync_script.exists():
        logger.error("Sync script not found at %s", sync_script)
        print("Sync script not found:", sync_script)
        return 2

    if once:
        run_sync_once(sync_script)
        return 0

    logger.info("Starting sync daemon with interval=%s seconds", interval)
    try:
        while True:
            run_sync_once(sync_script)
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Sync daemon interrupted by user")
    except Exception:
        logger.exception("Sync daemon error")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Open-OMS print sync job periodically.")
    parser.add_argument("--interval", "-i", type=int, default=10, help="Seconds between sync runs (default: 10)")
    parser.add_argument("--once", action="store_true", help="Run one sync iteration and exit")
    args = parser.parse_args()
    sys.exit(main(args.interval, args.once))
