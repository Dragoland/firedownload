"""Arranque de la aplicación: logging, QApplication, tema y ventana principal."""

from __future__ import annotations

import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from types import TracebackType

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from firedownload import __version__
from firedownload.config import Paths, Settings
from firedownload.core.manager import DownloadManager
from firedownload.core.tasks import shutdown_tasks
from firedownload.core.thumbs import ThumbnailLoader
from firedownload.core.utils import find_logo
from firedownload.ui.main_window import MainWindow
from firedownload.ui.theme import apply_theme

log = logging.getLogger("firedownload")


def _setup_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        Paths.ensure()
        handlers.append(RotatingFileHandler(Paths.LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _log_uncaught(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    log.critical("Excepción no capturada", exc_info=(exc_type, exc, tb))


def main() -> int:
    """Punto de entrada común a main.py y python -m firedownload."""
    _setup_logging()
    sys.excepthook = _log_uncaught

    app = QApplication(sys.argv)
    app.setApplicationName("FireDownload")
    app.setApplicationVersion(__version__)
    apply_theme(app)
    logo = find_logo()
    if logo is not None:
        app.setWindowIcon(QIcon(str(logo)))

    lock = QLockFile(str(Paths.LOCK_FILE))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200) and lock.error() == QLockFile.LockError.LockFailedError:
        QMessageBox.warning(None, "FireDownload", "FireDownload ya se está ejecutando.")
        return 1

    settings = Settings.load()
    manager = DownloadManager(settings)
    loader = ThumbnailLoader(app)
    app.aboutToQuit.connect(manager.shutdown)
    app.aboutToQuit.connect(shutdown_tasks)

    window = MainWindow(settings, manager, loader)
    window.show()

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer(app)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(250)

    return app.exec()
