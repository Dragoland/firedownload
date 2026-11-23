"""Cola de descargas: modelo de datos y orquestación de workers."""

from __future__ import annotations

import logging
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from firedownload.config import Settings, Sites, sanitize_options
from firedownload.core import history, queue_store, sounds
from firedownload.core.utils import parse_speed
from firedownload.core.worker import DownloadWorker

log = logging.getLogger(__name__)

_FORMAT_SUFFIX_RE = re.compile(r"\.f(?:\d+|hls|dash|http)[\w=+\-]*$")


class Status(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_FINISHED = frozenset({Status.COMPLETED, Status.FAILED, Status.CANCELLED})
_RESUMABLE = frozenset({Status.PENDING, Status.QUEUED, Status.DOWNLOADING, Status.PAUSED})


def _title_from_path(path: str) -> str:
    """Título legible a partir del nombre de archivo (sin sufijo de formato de yt-dlp)."""
    return _FORMAT_SUFFIX_RE.sub("", Path(path).stem)


@dataclass
class DownloadItem:
    """Estado de una descarga."""

    url: str
    options: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Status = Status.QUEUED
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    file_path: str = ""
    title: str = ""
    thumbnail: str = ""
    error_message: str = ""
    details: str = ""
    phase: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.url

    @property
    def finished(self) -> bool:
        return self.status in _FINISHED

    def to_history(self) -> dict[str, Any]:
        """Entrada serializable para history.json."""
        audio = bool(self.options.get("audio_only"))
        return {
            "date": (self.end_time or datetime.now()).isoformat(timespec="seconds"),
            "title": self.display_title,
            "url": self.url,
            "site": Sites.detect(self.url),
            "path": self.file_path,
            "quality": "Audio" if audio else self.options.get("quality", ""),
            "format": self.options.get("audio_format" if audio else "video_format", ""),
            "audio_only": audio,
        }


class DownloadManager(QObject):
    """Gestiona la cola, la concurrencia y el ciclo de vida de los workers."""

    item_added = Signal(str)
    item_removed = Signal(str)
    progress_updated = Signal(str)
    status_changed = Signal(str)
    queue_changed = Signal()
    order_changed = Signal()
    download_finished = Signal(str, bool)

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.queue: deque[DownloadItem] = deque()
        self.active: dict[str, DownloadWorker] = {}
        self.paused: dict[str, DownloadWorker] = {}
        self.items: dict[str, DownloadItem] = {}
        self._closing = False
        for signal in (self.item_added, self.item_removed, self.status_changed, self.order_changed):
            signal.connect(self._persist)

    @property
    def busy(self) -> bool:
        return bool(self.queue or self.active or self.paused)

    def add(
        self,
        url: str,
        options: dict[str, Any] | None = None,
        *,
        title: str = "",
        thumbnail: str = "",
    ) -> DownloadItem:
        """Encola una descarga y arranca si hay hueco."""
        item = DownloadItem(
            url=url,
            options=dict(options or self._settings.download_options()),
            title=title,
            thumbnail=thumbnail,
        )
        self.items[item.id] = item
        self.queue.append(item)
        self.item_added.emit(item.id)
        self.queue_changed.emit()
        self._pump()
        return item

    def restore(self) -> int:
        """Recupera la cola guardada como «pendiente» (el usuario decide cuándo reanudar)."""
        restored = 0
        for entry in queue_store.load():
            item = DownloadItem(
                url=entry["url"],
                options=sanitize_options(entry.get("options")),
                title=str(entry.get("title") or ""),
                thumbnail=str(entry.get("thumbnail") or ""),
                status=Status.PENDING,
            )
            self.items[item.id] = item
            self.item_added.emit(item.id)
            restored += 1
        return restored

    def start_pending(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.status is not Status.PENDING:
            return
        item.status = Status.QUEUED
        self.queue.append(item)
        self.status_changed.emit(item_id)
        self.queue_changed.emit()
        self._pump()

    def move(self, item_id: str, offset: int) -> None:
        """Mueve una descarga en cola `offset` posiciones (negativo = antes)."""
        item = self.items.get(item_id)
        if item is None or item.status is not Status.QUEUED:
            return
        queue = list(self.queue)
        index = queue.index(item)
        target = min(max(index + offset, 0), len(queue) - 1)
        if target == index:
            return
        queue.insert(target, queue.pop(index))
        self.queue = deque(queue)
        self._sync_items_order()
        self.order_changed.emit()
        self.queue_changed.emit()

    def prioritize(self, item_id: str) -> None:
        """Pone una descarga en cola la primera."""
        self.move(item_id, -len(self.queue))

    def _sync_items_order(self) -> None:
        """Refleja el orden de la cola en `items` (las demás posiciones no cambian)."""
        ids = list(self.items)
        slots = [n for n, key in enumerate(ids) if self.items[key].status is Status.QUEUED]
        for slot, item in zip(slots, self.queue):
            ids[slot] = item.id
        self.items = {key: self.items[key] for key in ids}

    def pause_all(self) -> None:
        for item_id in list(self.active):
            self.pause(item_id)

    def resume_all(self) -> None:
        for item_id in list(self.paused):
            self.resume(item_id)

    def total_speed(self) -> float:
        """Suma de la velocidad (bytes/s) de las descargas activas."""
        return sum(parse_speed(self.items[i].speed) for i in self.active if i in self.items)

    def resume_pending(self) -> None:
        for item in [i for i in self.items.values() if i.status is Status.PENDING]:
            self.start_pending(item.id)

    def pause(self, item_id: str) -> None:
        worker = self.active.pop(item_id, None)
        item = self.items.get(item_id)
        if worker is None or item is None:
            return
        worker.pause()
        self.paused[item_id] = worker
        item.status = Status.PAUSED
        self.status_changed.emit(item_id)
        self._pump()

    def resume(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is not None and item.status is Status.PENDING:
            self.start_pending(item_id)
            return
        worker = self.paused.pop(item_id, None)
        if worker is None or item is None:
            return
        worker.resume()
        self.active[item_id] = worker
        item.status = Status.DOWNLOADING
        self.status_changed.emit(item_id)

    def cancel(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.finished:
            return
        if item.status in (Status.QUEUED, Status.PENDING):
            self.queue = deque(i for i in self.queue if i is not item)
            item.status = Status.CANCELLED
            item.end_time = datetime.now()
            self.status_changed.emit(item_id)
            self.queue_changed.emit()
            return
        worker = self.active.get(item_id) or self.paused.get(item_id)
        if worker is not None:
            worker.cancel()

    def retry(self, item_id: str) -> None:
        """Vuelve a encolar una descarga fallida o cancelada."""
        item = self.items.get(item_id)
        if item is None or item.status not in (Status.FAILED, Status.CANCELLED):
            return
        self.remove(item_id)
        self.add(item.url, item.options, title=item.title, thumbnail=item.thumbnail)

    def remove(self, item_id: str) -> None:
        """Quita de la lista una descarga terminada (no toca el historial)."""
        item = self.items.get(item_id)
        if item is None or not item.finished:
            return
        del self.items[item_id]
        self.item_removed.emit(item_id)

    def clear_finished(self) -> None:
        for item in [i for i in self.items.values() if i.finished]:
            self.remove(item.id)

    def _persist(self, *_args: Any) -> None:
        """Guarda en disco lo que aún no ha terminado."""
        if self._closing:
            return
        entries = [
            {"url": i.url, "options": i.options, "title": i.title, "thumbnail": i.thumbnail}
            for i in self.items.values()
            if i.status in _RESUMABLE
        ]
        try:
            queue_store.save(entries)
        except OSError:
            log.exception("No se pudo guardar la cola")

    def apply_settings(self) -> None:
        """Reevalúa la cola tras cambiar la concurrencia."""
        self._pump()

    def shutdown(self) -> None:
        """Guarda la cola, cancela todo y espera a los hilos (al cerrar la aplicación)."""
        self._persist()
        self._closing = True
        workers = [*self.active.values(), *self.paused.values()]
        for worker in workers:
            worker.cancel()
        for worker in workers:
            worker.wait(5000)

    def _pump(self) -> None:
        started = False
        limit = max(1, self._settings.max_concurrent)
        while self.queue and len(self.active) < limit:
            item = self.queue.popleft()
            worker = DownloadWorker(item.id, item.url, item.options, self)
            worker.progress.connect(self._on_progress)
            worker.destination.connect(self._on_destination)
            worker.phase.connect(self._on_phase)
            worker.finished_sig.connect(self._on_finished)
            self.active[item.id] = worker
            item.status = Status.DOWNLOADING
            item.start_time = datetime.now()
            self.status_changed.emit(item.id)
            worker.start()
            started = True
        if started:
            self.queue_changed.emit()

    @Slot(str, float, str, str)
    def _on_progress(self, item_id: str, percent: float, speed: str, eta: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.finished:
            return
        item.progress, item.speed, item.eta, item.phase = percent, speed, eta, ""
        self.progress_updated.emit(item.id)

    @Slot(str, str)
    def _on_destination(self, item_id: str, path: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.finished:
            return
        item.file_path = path
        item.title = item.title or _title_from_path(path)
        self.progress_updated.emit(item.id)

    @Slot(str, str)
    def _on_phase(self, item_id: str, text: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.finished:
            return
        item.phase = text
        self.progress_updated.emit(item.id)

    @Slot(str, bool, str, str)
    def _on_finished(self, item_id: str, ok: bool, message: str, file_path: str) -> None:
        worker = self.active.pop(item_id, None) or self.paused.pop(item_id, None)
        self.active.pop(item_id, None)
        self.paused.pop(item_id, None)
        if worker is None:
            return
        worker.wait()
        worker.deleteLater()

        item = self.items.get(item_id)
        if item is not None:
            if not ok and not worker.cancelled:
                item.details = worker.diagnostics()
            self._finalize(item, worker.cancelled, ok, message, file_path)
        self.queue_changed.emit()
        self._pump()

    def _finalize(self, item: DownloadItem, cancelled: bool, ok: bool, message: str, file_path: str) -> None:
        item.end_time = datetime.now()
        item.speed = item.eta = item.phase = ""
        if ok:
            item.status = Status.COMPLETED
            item.progress = 100.0
            if file_path:
                item.file_path = file_path
                item.title = item.title or _title_from_path(file_path)
            if item.file_path:
                try:
                    history.add(item.to_history())
                except OSError:
                    log.exception("No se pudo guardar el historial")
            if self._settings.enable_sounds:
                sounds.play_complete()
        elif cancelled:
            item.status = Status.CANCELLED
        else:
            item.status = Status.FAILED
            item.error_message = message
            log.warning("Descarga fallida (%s): %s", item.url, message)
            if self._settings.enable_sounds:
                sounds.play_error()
        self.status_changed.emit(item.id)
        self.download_finished.emit(item.id, ok)
