"""Descarga de miniaturas con caché en disco (por MD5 de la URL) y en memoria."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from firedownload.config import Paths

log = logging.getLogger(__name__)

_MAX_FILES = 500
_MAX_MEMORY = 200


def cover(pixmap: QPixmap, width: int, height: int) -> QPixmap:
    """Escala y recorta al centro para llenar exactamente width×height."""
    scaled = pixmap.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    return scaled.copy((scaled.width() - width) // 2, (scaled.height() - height) // 2, width, height)


class ThumbnailLoader(QObject):
    """Pide miniaturas por URL y emite `loaded(url, pixmap)` en el hilo principal."""

    loaded = Signal(str, QPixmap)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._net = QNetworkAccessManager(self)
        self._pending: set[str] = set()
        self._memory: dict[str, QPixmap] = {}
        self._prune()

    def request(self, url: str) -> None:
        if not url:
            return
        pixmap = self._memory.get(url) or self._from_disk(url)
        if pixmap is not None:
            self._remember(url, pixmap)
            QTimer.singleShot(0, lambda: self.loaded.emit(url, pixmap))
            return
        if url in self._pending:
            return
        self._pending.add(url)
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0")
        reply = self._net.get(request)
        reply.finished.connect(lambda: self._on_reply(url, reply))

    def _path(self, url: str) -> Path:
        return Paths.CACHE / (hashlib.md5(url.encode("utf-8")).hexdigest() + ".img")

    def _from_disk(self, url: str) -> QPixmap | None:
        path = self._path(url)
        if not path.is_file():
            return None
        pixmap = QPixmap(str(path))
        return None if pixmap.isNull() else pixmap

    def _remember(self, url: str, pixmap: QPixmap) -> None:
        if len(self._memory) >= _MAX_MEMORY:
            self._memory.clear()
        self._memory[url] = pixmap

    def _on_reply(self, url: str, reply: QNetworkReply) -> None:
        self._pending.discard(url)
        data = reply.readAll()
        error = reply.error()
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            log.debug("Miniatura no disponible (%s): %s", url, error)
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        try:
            Paths.CACHE.mkdir(parents=True, exist_ok=True)
            self._path(url).write_bytes(bytes(data))
        except OSError:
            log.debug("No se pudo cachear la miniatura", exc_info=True)
        self._remember(url, pixmap)
        self.loaded.emit(url, pixmap)

    def _prune(self) -> None:
        try:
            files = sorted(Paths.CACHE.glob("*.img"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in files[_MAX_FILES:]:
                old.unlink(missing_ok=True)
        except OSError:
            log.debug("No se pudo limpiar la caché", exc_info=True)
