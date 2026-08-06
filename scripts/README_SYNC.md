# Open-OMS Sync Daemon — Deployment Notes

This repository includes two production-friendly options to run the print sync every 10 seconds:

- Lightweight daemon (cross-platform): `scripts/sync_print_daemon.py` — intended to be launched from a supervisor or service manager.
- Windows Service wrapper (pywin32): `scripts/openoms_sync_service.py` — registerable via the included batch helpers.

Install (Windows, recommended for production):

1. Ensure the repo `.venv` is created and required packages are installed, including `pywin32`:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install pywin32
```

2. Install and start the Windows service (run as Administrator):

```powershell
.\scripts\install_sync_service.bat
```

3. To uninstall:

```powershell
.\scripts\uninstall_sync_service.bat
```

Notes:
- The service runs `sync_print_daemon.py` with `-i 10` (10s interval) and will automatically restart the daemon if it exits.
- If you prefer using NSSM or another service manager, the daemon script is compatible — point the service command to `python .\scripts\sync_print_daemon.py -i 10`.


---
*Graph Context: Return to [[Home]] (Architecture)*
