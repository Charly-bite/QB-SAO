import os
import sys
import time
import subprocess

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except Exception:
    print("pywin32 is required to run this service. Install with: pip install pywin32")
    raise


class SyncService(win32serviceutil.ServiceFramework):
    _svc_name_ = "OpenOMSPrintSync"
    _svc_display_name_ = "Open-OMS Print Sync Daemon"
    _svc_description_ = "Runs the Open-OMS print sync daemon and restarts on failure."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(5)
            except Exception:
                pass
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("Open-OMS Sync Service starting")
        self.main()

    def main(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        daemon_script = os.path.join(script_dir, "sync_print_daemon.py")
        python_exe = sys.executable

        while True:
            # Check stop signal
            rc = win32event.WaitForSingleObject(self.hWaitStop, 0)
            if rc == win32event.WAIT_OBJECT_0:
                break

            # Start the daemon subprocess
            try:
                self.process = subprocess.Popen([python_exe, daemon_script, "-i", "10"], cwd=script_dir)
                servicemanager.LogInfoMsg(f"Started sync subprocess pid={self.process.pid}")
            except Exception as e:
                servicemanager.LogErrorMsg(f"Failed to start sync subprocess: {e}")
                # wait before retry
                time.sleep(5)
                continue

            # Monitor process and restart if it exits
            while True:
                rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                if rc == win32event.WAIT_OBJECT_0:
                    if self.process and self.process.poll() is None:
                        try:
                            self.process.terminate()
                            self.process.wait(5)
                        except Exception:
                            pass
                    return

                if self.process.poll() is not None:
                    servicemanager.LogInfoMsg(f"Sync subprocess exited with {self.process.returncode}; restarting")
                    time.sleep(1)
                    break


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(SyncService)
