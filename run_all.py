#!/usr/bin/env python3
"""
run_all.py

Convenient helper to launch the Smart India Hackathon backend (FastAPI)
and the frontend static‑file server in one process.

Usage:
    $ python run_all.py          # starts both services
    # then open http://localhost:5500 in a browser

Press Ctrl‑C to shut down both services cleanly.
"""

import subprocess
import sys
import signal
import threading
from pathlib import Path

# ----------------------------------------------------------------------
# Configuration – adjust only if you change ports or folder layout
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

# Backend directory should be the folder that contains the `app` package
BACKEND_DIR = PROJECT_ROOT / "back end"          # <-- parent of the app package
FRONTEND_DIR = PROJECT_ROOT / "public"           # holds index.html, etc.

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = "8000"
FRONTEND_HOST = "0.0.0.0"
FRONTEND_PORT = "5500"

# ----------------------------------------------------------------------
# Helper to run a subprocess and keep a reference for later termination
# ----------------------------------------------------------------------
class ProcWrapper:
    def __init__(self, args, cwd: Path, name: str):
        self.args = args
        self.cwd = cwd
        self.name = name
        self.proc: subprocess.Popen | None = None

    def start(self):
        print(f"[{self.name}] Starting: {' '.join(self.args)} (cwd={self.cwd})")
        self.proc = subprocess.Popen(
            self.args,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=self._stream_output, daemon=True).start()

    def _stream_output(self):
        assert self.proc is not None
        for line in self.proc.stdout:               # type: ignore[union-attr]
            sys.stdout.write(f"[{self.name}] {line}")

    def terminate(self):
        if self.proc and self.proc.poll() is None:
            print(f"[{self.name}] Terminating...")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"[{self.name}] Force‑killing...")
                self.proc.kill()


# ----------------------------------------------------------------------
# Start the backend (uvicorn) and the frontend (http.server)
# ----------------------------------------------------------------------
def main():
    # 1️⃣  Backend – uvicorn
    backend_cmd = [
        sys.executable,                     # use the same Python interpreter
        "-m",
        "uvicorn",
        "app.main:app",                     # import the FastAPI app
        "--host",
        BACKEND_HOST,
        "--port",
        BACKEND_PORT,
        "--reload",                         # hot‑reload for development
    ]
    # Note: cwd is the *parent* directory that contains the `app` package
    backend = ProcWrapper(backend_cmd, cwd=BACKEND_DIR, name="backend")
    backend.start()

    # 2️⃣  Front‑end – simple static server
    frontend_cmd = [
        sys.executable,
        "-m",
        "http.server",
        FRONTEND_PORT,
        "--bind",
        FRONTEND_HOST,
    ]
    frontend = ProcWrapper(frontend_cmd, cwd=FRONTEND_DIR, name="frontend")
    frontend.start()

    # --------------------------------------------------------------
    # Graceful shutdown on Ctrl‑C (SIGINT) or termination signal
    # --------------------------------------------------------------
    def shutdown(_sig=None, _frame=None):
        print("\nReceived interrupt – shutting down services...")
        frontend.terminate()
        backend.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep the main thread alive while the child processes run
    try:
        while True:
            if backend.proc and backend.proc.poll() is not None:
                print("[backend] exited unexpectedly – stopping frontend")
                frontend.terminate()
                break
            if frontend.proc and frontend.proc.poll() is not None:
                print("[frontend] exited unexpectedly – stopping backend")
                backend.terminate()
                break
            # Sleep briefly; no busy‑wait.
            signal.pause()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()