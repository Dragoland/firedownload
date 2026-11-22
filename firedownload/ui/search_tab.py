"""Pestaña de búsqueda: busca en YouTube o SoundCloud con yt-dlp."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firedownload.config import SEARCH_LIMIT, SEARCH_SOURCES, Settings
from firedownload.core.info import SearchResult, parse_search, search_args
from firedownload.core.tasks import YtdlpTask
from firedownload.core.thumbs import ThumbnailLoader, cover
from firedownload.core.utils import format_duration
from firedownload.core.ytdlp import ytdlp_command

_ICON_W, _ICON_H = 128, 72


class SearchTab(QWidget):
    """Buscador con miniaturas; permite descargar o ver detalles de un resultado."""

    download_requested = Signal(str, str, str)
    details_requested = Signal(str)

    def __init__(self, settings: Settings, loader: ThumbnailLoader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._loader = loader
        self._task: YtdlpTask | None = None
        self._rows: dict[str, list[QListWidgetItem]] = {}
        placeholder = QPixmap(_ICON_W, _ICON_H)
        placeholder.fill(QColor("#0a0f15"))
        self._placeholder = QIcon(placeholder)

        self._query = QLineEdit()
        self._query.setPlaceholderText("Buscar vídeos o música…")
        self._query.setClearButtonEnabled(True)
        self._source = QComboBox()
        self._source.addItems(list(SEARCH_SOURCES))
        self._go = QPushButton("Buscar")
        self._go.setObjectName("primary")
        self._list = QListWidget()
        self._list.setIconSize(QSize(_ICON_W, _ICON_H))
        self._list.setSpacing(2)
        self._status = QLabel("Escribe qué buscar y pulsa Intro.")
        self._status.setObjectName("muted")
        self._download = QPushButton("Descargar")
        self._details = QPushButton("Detalles…")
        self._copy = QPushButton("Copiar URL")
        for button in (self._download, self._details, self._copy):
            button.setEnabled(False)

        top = QHBoxLayout()
        top.addWidget(self._query, 1)
        top.addWidget(self._source)
        top.addWidget(self._go)
        bottom = QHBoxLayout()
        bottom.addWidget(self._status, 1)
        bottom.addWidget(self._copy)
        bottom.addWidget(self._details)
        bottom.addWidget(self._download)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self._list, 1)
        layout.addLayout(bottom)

        self._query.returnPressed.connect(self._search)
        self._go.clicked.connect(self._search)
        self._list.itemSelectionChanged.connect(self._sync_buttons)
        self._list.itemDoubleClicked.connect(lambda _item: self._emit_details())
        self._download.clicked.connect(self._emit_download)
        self._details.clicked.connect(self._emit_details)
        self._copy.clicked.connect(self._copy_url)
        loader.loaded.connect(self._on_thumbnail)

    def focus_query(self) -> None:
        self._query.setFocus()
        self._query.selectAll()

    def _selected(self) -> SearchResult | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _sync_buttons(self) -> None:
        enabled = self._selected() is not None
        for button in (self._download, self._details, self._copy):
            button.setEnabled(enabled)

    def _search(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        prefix = SEARCH_SOURCES[self._source.currentText()]
        command = ytdlp_command(search_args(prefix, query, SEARCH_LIMIT, self._settings.download_options()))
        if command is None:
            QMessageBox.critical(self, "yt-dlp no encontrado", "Instala yt-dlp con «pip install yt-dlp».")
            return
        self._drop_task()
        self._task = YtdlpTask(command)
        self._task.succeeded.connect(self._on_results)
        self._task.failed.connect(self._on_failed)
        self._go.setEnabled(False)
        self._status.setText("Buscando…")
        self._task.start()

    def _drop_task(self) -> None:
        """Descarta la búsqueda anterior para que sus resultados no lleguen tarde."""
        task, self._task = self._task, None
        if task is None:
            return
        for signal, slot in ((task.succeeded, self._on_results), (task.failed, self._on_failed)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        task.requestInterruption()

    def _on_failed(self, message: str) -> None:
        self._go.setEnabled(True)
        self._status.setText(f"Error en la búsqueda: {message}")

    def _on_results(self, raw: str) -> None:
        self._go.setEnabled(True)
        try:
            results = parse_search(raw)
        except ValueError as exc:
            self._status.setText(f"Respuesta no válida de yt-dlp: {exc}")
            return
        self._list.clear()
        self._rows = {}
        for result in results:
            details = " · ".join(p for p in (result.channel, format_duration(result.duration)) if p)
            item = QListWidgetItem(self._placeholder, f"{result.title}\n{details}")
            item.setData(Qt.ItemDataRole.UserRole, result)
            self._list.addItem(item)
            if result.thumbnail:
                self._rows.setdefault(result.thumbnail, []).append(item)
                self._loader.request(result.thumbnail)
        self._status.setText(f"{len(results)} resultados" if results else "Sin resultados.")
        self._sync_buttons()

    def _on_thumbnail(self, url: str, pixmap: QPixmap) -> None:
        icon = QIcon(cover(pixmap, _ICON_W, _ICON_H))
        for item in self._rows.get(url, []):
            item.setIcon(icon)

    def _emit_download(self) -> None:
        result = self._selected()
        if result is not None:
            self.download_requested.emit(result.url, result.title, result.thumbnail)

    def _emit_details(self) -> None:
        result = self._selected()
        if result is not None:
            self.details_requested.emit(result.url)

    def _copy_url(self) -> None:
        result = self._selected()
        if result is not None:
            QGuiApplication.clipboard().setText(result.url)
