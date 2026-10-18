"""ACS AI V2 Persistent Daemon.
Supervises background mission execution, provides the Local API server,
enforces single-writer SQLite access, and performs crash recovery.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Optional

from .api_server import ACSServer
from .auth import get_or_create_auth_token
from .config import API_HOST, API_PORT, DB_PATH, LOGS_DIR, PID_FILE, STATE_DIR
from .db import DatabaseManager
from .state_machine import StateMachine
from .service_lock import ServiceLock
from .security import RedactingFormatter
from logging.handlers import RotatingFileHandler
from .watchdog import notify

# Configure logging
LOG_FILE = LOGS_DIR / "daemon.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
for handler in logging.getLogger().handlers:
    handler.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger = logging.getLogger("acs_ai.daemon")

STATUS_FILE = STATE_DIR / "daemon.json"


class ACSDaemon:
    def __init__(self, host: str = API_HOST, port: int = API_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.db = DatabaseManager(DB_PATH, read_only=False)
        self.state_machine = StateMachine(self.db)
        self.auth_token = get_or_create_auth_token()
        self.http_server: Optional[ACSServer] = None
        self.http_thread: Optional[threading.Thread] = None
        self.last_backup = 0.0
        from .daemon_dispatch import DaemonDispatcher
        self.dispatcher = DaemonDispatcher(self.db)
        self.service_lock: Optional[ServiceLock] = None

    def _periodic_backup(self) -> None:
        if os.environ.get("ACS_ENABLE_PERIODIC_BACKUPS") != "1":
            return
        interval = max(60, int(os.environ.get("ACS_BACKUP_INTERVAL_SECONDS", "3600")))
        if self.last_backup and time.monotonic() - self.last_backup < interval:
            return
        from .config import BACKUPS_DIR
        from .recovery import create_backup
        import uuid
        create_backup(DB_PATH, BACKUPS_DIR / f"scheduled-{uuid.uuid4().hex}.acs-backup")
        self.last_backup = time.monotonic()

    def start(self) -> None:
        """Starts the persistent daemon and API server."""
        self.service_lock = ServiceLock(STATE_DIR / 'daemon.lock').acquire()
        if PID_FILE.exists():
            from .supervision import identity
            previous = PID_FILE.read_text().strip()
            if previous.isdigit() and int(previous) != os.getpid() and identity(int(previous)) is not None:
                self.service_lock.release()
                raise RuntimeError('Existing daemon PID is live; stop it explicitly before starting a replacement')
        self.running = True
        logger.info(f"Starting ACS AI Persistent Daemon on {self.host}:{self.port}...")

        # Record PID
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        self._update_status("running")

        # Setup Signal Handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # Gate 2 Safeguard: Reconcile interrupted missions from previous crashes
        logger.info("Executing startup crash reconciliation check...")
        reconciled = self.state_machine.reconcile_interrupted_missions()
        if reconciled:
            logger.info(f"Reconciled {len(reconciled)} interrupted mission(s) from previous unclean shutdown.")

        # Start HTTP API Server in separate thread
        try:
            self.http_server = ACSServer(self.host, self.port, self.db, self.auth_token)
            self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_thread.start()
            logger.info(f"Local API Server listening on http://{self.host}:{self.port}")
            notify("READY=1")
        except Exception as e:
            logger.error(f"Failed to bind Local API Server: {e}")
            self.stop()
            raise

        logger.info("Daemon initialization complete. Entering supervisor loop.")
        self._run_loop()

    def _run_loop(self) -> None:
        """Main supervisor loop processing queued tasks and checking resource limits."""
        while self.running:
            try:
                if os.environ.get('ACS_ENABLE_DAEMON_EXECUTION') == '1':
                    self.dispatcher.tick()

                # Update heartbeat in status file
                self._update_status("running")
                if self.http_thread and self.http_thread.is_alive():
                    notify("WATCHDOG=1")
                self._periodic_backup()
                time.sleep(2.0)
            except Exception as e:
                logger.error(f"Error in daemon supervisor loop: {e}")
                time.sleep(5.0)

    def _update_status(self, state: str) -> None:
        try:
            status_data = {
                "state": state,
                "pid": os.getpid(),
                "host": self.host,
                "port": self.port,
                "db_path": str(DB_PATH),
                "last_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            STATUS_FILE.write_text(json.dumps(status_data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to update daemon status file: {e}")

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}; initiating graceful shutdown...")
        self.stop()

    def stop(self) -> None:
        """Gracefully shuts down the daemon and frees ports and resources."""
        self.running = False
        notify("STOPPING=1")
        dispatcher = getattr(self, 'dispatcher', None)
        if dispatcher:
            dispatcher.close()
        if self.http_server:
            try:
                self.http_server.shutdown()
                self.http_server.server_close()
                logger.info("HTTP Server stopped.")
            except Exception as e:
                logger.warning(f"Error closing HTTP server: {e}")

        self._update_status("stopped")
        if PID_FILE.exists():
            try:
                if PID_FILE.read_text().strip() == str(os.getpid()):
                    PID_FILE.unlink()
            except Exception:
                pass
        service_lock = getattr(self, 'service_lock', None)
        if service_lock:
            service_lock.release()
        logger.info("ACS AI Persistent Daemon stopped cleanly.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="ACS AI Persistent Daemon")
    parser.add_argument("--host", default=API_HOST, help="API server bind host")
    parser.add_argument("--port", type=int, default=API_PORT, help="API server bind port")
    args = parser.parse_args()

    daemon = ACSDaemon(host=args.host, port=args.port)
    daemon.start()


if __name__ == "__main__":
    main()
