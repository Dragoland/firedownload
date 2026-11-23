"""Arranque de la aplicación: logging, instancia única, QApplication, tema y ventana principal."""

from __future__ import annotations

import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from firedownload import __version__
from firedownload.config import Paths, Settings
from firedownload.core.manager import DownloadManager
from firedownload.core.single_instance import SingleInstance
from firedownload.core.tasks import shutdown_tasks
from firedownload.core.thumbs import ThumbnailLoader
from firedownload.core.utils import find_logo, validate_url
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


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada común a main.py y python -m firedownload. Las URLs pasadas como argumentos se añaden."""
    _setup_logging()
    sys.excepthook = _log_uncaught
    urls = [arg for arg in (argv if argv is not None else sys.argv[1:]) if validate_url(arg)]

    app = QApplication(sys.argv[:1])
    instance = SingleInstance(parent=app)
    if instance.send_to_running("\n".join(["SHOW", *urls])):
        return 0
    instance.listen()

    app.setApplicationName("FireDownload")
    app.setApplicationVersion(__version__)
    apply_theme(app)
    logo = find_logo()
    if logo is not None:
        app.setWindowIcon(QIcon(str(logo)))

    settings = Settings.load()
    manager = DownloadManager(settings)
    loader = ThumbnailLoader(app)
    app.aboutToQuit.connect(manager.shutdown)
    app.aboutToQuit.connect(shutdown_tasks)

    window = MainWindow(settings, manager, loader)
    instance.message_received.connect(window.handle_external)
    window.show()
    if urls:
        QTimer.singleShot(0, lambda: window.handle_external("\n".join(urls)))

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer(app)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(250)

    return app.exec()
