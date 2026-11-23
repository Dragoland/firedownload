"""Pestaña de descargas: alta de URLs, tarjetas de progreso y acciones."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from firedownload.config import AUDIO_FORMATS, QUALITIES, VIDEO_FORMATS, Settings, Sites
from firedownload.core import profiles
from firedownload.core.manager import DownloadItem, DownloadManager, Status
from firedownload.core.thumbs import ThumbnailLoader, cover
from firedownload.core.utils import (
    check_ffmpeg,
    find_js_runtime,
    find_ytdlp,
    format_size,
    free_space,
    is_playlist_url,
    open_file,
    open_in_file_manager,
    validate_url,
)

log = logging.getLogger(__name__)

_CARD_THUMB = (112, 63)
MIN_FREE_BYTES = 500 * 1024 * 1024


class ElidedLabel(QLabel):
    """Etiqueta de una línea que recorta con «…» según el ancho disponible."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        if text == self._full:
            return
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self.width(), 10)
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, width))


class DownloadCard(QFrame):
    """Tarjeta con miniatura, título, progreso, estado y acciones de una descarga."""

    def __init__(
        self,
        item: DownloadItem,
        manager: DownloadManager,
        loader: ThumbnailLoader,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._manager = manager
        self._shown_status: Status | None = None
        self.setObjectName("card")

        self._thumb = QLabel()
        self._thumb.setObjectName("thumb")
        self._thumb.setFixedSize(*_CARD_THUMB)
        self._thumb.setVisible(bool(item.thumbnail))
        self._title = ElidedLabel()
        self._title.setObjectName("title")
        self._meta = QLabel(self._meta_text())
        self._meta.setObjectName("muted")
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._state = QLabel()
        self._state.setObjectName("state")
        self._state.setWordWrap(True)

        self._toggle = QPushButton("Pausar")
        self._cancel = QPushButton("Cancelar")
        self._cancel.setObjectName("danger")
        self._play = QPushButton("Reproducir")
        self._open = QPushButton("Abrir carpeta")
        self._retry = QPushButton("Reintentar")
        self._copy = QPushButton("Copiar detalle")
        self._up = QPushButton("▲")
        self._down = QPushButton("▼")
        self._first = QPushButton("Primero")
        self._up.setToolTip("Subir en la cola")
        self._down.setToolTip("Bajar en la cola")
        self._first.setToolTip("Descargar esta la primera")
        self._remove = QPushButton("Quitar")
        self._toggle.clicked.connect(self._on_toggle)
        self._cancel.clicked.connect(lambda: manager.cancel(item.id))
        self._play.clicked.connect(self._play_file)
        self._open.clicked.connect(self._open_folder)
        self._retry.clicked.connect(lambda: manager.retry(item.id))
        self._copy.clicked.connect(self._copy_details)
        self._up.clicked.connect(lambda: manager.move(item.id, -1))
        self._down.clicked.connect(lambda: manager.move(item.id, 1))
        self._first.clicked.connect(lambda: manager.prioritize(item.id))
        self._remove.clicked.connect(lambda: manager.remove(item.id))

        bottom = QHBoxLayout()
        bottom.addWidget(self._state, 1)
        for button in (self._up, self._down, self._first, self._toggle, self._cancel, self._play, self._open, self._retry, self._copy, self._remove):
            bottom.addWidget(button)
        body = QVBoxLayout()
        body.setSpacing(6)
        body.addWidget(self._title)
        body.addWidget(self._meta)
        body.addWidget(self._bar)
        body.addLayout(bottom)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self._thumb, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body, 1)

        if item.thumbnail:
            loader.loaded.connect(self._on_thumbnail)
            loader.request(item.thumbnail)
        self.refresh()

    def _on_thumbnail(self, url: str, pixmap: QPixmap) -> None:
        if url == self._item.thumbnail:
            self._thumb.setPixmap(cover(pixmap, *_CARD_THUMB))

    def refresh(self) -> None:
        """Sincroniza la tarjeta con el estado del DownloadItem."""
        item, status = self._item, self._item.status
        self._title.set_full_text(item.display_title)
        self._bar.setValue(int(item.progress * 10))
        self._state.setText(self._state_text())

        if status is not self._shown_status:
            self._shown_status = status
            self._state.setProperty("status", status.value)
            self._state.style().unpolish(self._state)
            self._state.style().polish(self._state)
            running = status in (Status.DOWNLOADING, Status.PAUSED)
            waiting = status is Status.PENDING
            self._toggle.setVisible(running or waiting)
            self._toggle.setText("Reanudar" if status in (Status.PAUSED, Status.PENDING) else "Pausar")
            self._cancel.setVisible(running or waiting or status is Status.QUEUED)
            self._copy.setVisible(status is Status.FAILED)
            for button in (self._up, self._down, self._first):
                button.setVisible(status is Status.QUEUED)
            self._play.setVisible(status is Status.COMPLETED)
            self._open.setVisible(status is Status.COMPLETED)
            self._retry.setVisible(status in (Status.FAILED, Status.CANCELLED))
            self._remove.setVisible(item.finished)

    def _meta_text(self) -> str:
        options = self._item.options
        if options.get("subs_mode") == "only" and options.get("subs_langs"):
            detail = "Subtítulos · " + ",".join(options["subs_langs"])
        elif options.get("audio_only"):
            detail = f"Audio · {options.get('audio_format', '')}"
        else:
            detail = f"{options.get('quality', '')} · {options.get('video_format', '')}"
            if len(options.get("audio_langs") or []) > 1:
                detail += f" · {len(options['audio_langs'])} pistas"
        if options.get("download_playlist"):
            detail += " · Playlist"
        return f"{Sites.detect(self._item.url)} · {detail}"

    def _state_text(self) -> str:
        item = self._item
        if item.status is Status.DOWNLOADING:
            if item.phase:
                return item.phase
            if item.progress == 0 and not item.speed:
                return "Iniciando…"
            parts = [f"{item.progress:.1f}%"]
            if item.speed:
                parts.append(item.speed)
            if item.eta:
                parts.append(f"ETA {item.eta}")
            return " · ".join(parts)
        if item.status is Status.PAUSED:
            return f"En pausa · {item.progress:.1f}%"
        if item.status is Status.FAILED:
            return f"Error: {item.error_message}"
        return {
            Status.PENDING: "Pendiente de la sesión anterior · pulsa Reanudar",
            Status.QUEUED: "En cola",
            Status.COMPLETED: "Completado",
            Status.CANCELLED: "Cancelado",
        }[item.status]

    def _on_toggle(self) -> None:
        if self._item.status in (Status.PAUSED, Status.PENDING):
            self._manager.resume(self._item.id)
        else:
            self._manager.pause(self._item.id)

    def _copy_details(self) -> None:
        item = self._item
        report = f"URL: {item.url}\nError: {item.error_message}\n\n{item.details}"
        QGuiApplication.clipboard().setText(report)

    def _play_file(self) -> None:
        if not self._item.file_path or not open_file(Path(self._item.file_path)):
            QMessageBox.warning(self, "No se pudo abrir", "El archivo ya no existe o no tiene reproductor asociado.")

    def _open_folder(self) -> None:
        item = self._item
        target = Path(item.file_path or str(item.options.get("download_path", "")))
        if not open_in_file_manager(target):
            QMessageBox.warning(self, "No se pudo abrir", f"No se encontró la ruta:\n{target}")


class DownloadTab(QWidget):
    """Formulario de alta de descargas y lista de tarjetas."""

    analyze_requested = Signal(str, bool)
    tools_requested = Signal()
    status_message = Signal(str)

    def __init__(
        self,
        settings: Settings,
        manager: DownloadManager,
        loader: ThumbnailLoader,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._manager = manager
        self._loader = loader
        self._cards: dict[str, DownloadCard] = {}
        self.setAcceptDrops(True)

        self._url = QLineEdit()
        self._url.setPlaceholderText("Pega una o varias URLs (separadas por espacio)…")
        self._url.setClearButtonEnabled(True)
        self._analyze = QPushButton("Analizar…")
        self._add = QPushButton("Añadir")
        self._add.setObjectName("primary")
        self._import = QPushButton("Importar lista…")

        self._quality = QComboBox()
        self._quality.addItems(QUALITIES)
        self._quality.setCurrentText(settings.quality)
        self._video_format = QComboBox()
        self._video_format.addItems(VIDEO_FORMATS)
        self._video_format.setCurrentText(settings.video_format)
        self._audio_only = QCheckBox("Solo audio")
        self._audio_only.setChecked(settings.audio_only)
        self._audio_format = QComboBox()
        self._audio_format.addItems(AUDIO_FORMATS)
        self._audio_format.setCurrentText(settings.audio_format)
        self._playlist = QCheckBox("Playlist completa")
        self._playlist.setChecked(settings.download_playlist)

        self._summary = QLabel()
        self._summary.setObjectName("muted")
        self._clear = QPushButton("Quitar terminados")
        self._resume_pending = QPushButton("Reanudar pendientes")
        self._resume_pending.setObjectName("primary")
        self._resume_pending.setVisible(False)
        self._empty = QLabel("Aún no hay descargas. Pega una URL, arrástrala aquí o usa la pestaña Buscar.")
        self._empty.setObjectName("muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._banner_label = QLabel()
        self._banner_label.setObjectName("warning")
        self._banner_label.setWordWrap(True)
        self._banner_button = QPushButton("Instalar…")
        self._banner_button.setObjectName("primary")
        self._banner_button.clicked.connect(self.tools_requested)
        self._banner = QWidget()
        banner_row = QHBoxLayout(self._banner)
        banner_row.setContentsMargins(0, 0, 0, 0)
        banner_row.addWidget(self._banner_label, 1)
        banner_row.addWidget(self._banner_button)

        self._profile = QComboBox()
        self._profile_save = QPushButton("Guardar perfil…")
        self._profile_delete = QPushButton("Eliminar")
        self._profile_extra: dict[str, object] = {}

        url_row = QHBoxLayout()
        url_row.addWidget(self._url, 1)
        url_row.addWidget(self._analyze)
        url_row.addWidget(self._add)

        options_row = QHBoxLayout()
        options_row.setSpacing(8)
        for text, widget in (("Calidad", self._quality), ("Formato", self._video_format)):
            label = QLabel(text)
            label.setObjectName("muted")
            options_row.addWidget(label)
            options_row.addWidget(widget)
        options_row.addSpacing(12)
        options_row.addWidget(self._audio_only)
        options_row.addWidget(self._audio_format)
        options_row.addSpacing(12)
        options_row.addWidget(self._playlist)
        options_row.addStretch(1)
        options_row.addWidget(self._import)

        profile_row = QHBoxLayout()
        profile_label = QLabel("Perfil")
        profile_label.setObjectName("muted")
        profile_row.addWidget(profile_label)
        profile_row.addWidget(self._profile, 1)
        profile_row.addWidget(self._profile_save)
        profile_row.addWidget(self._profile_delete)

        status_row = QHBoxLayout()
        status_row.addWidget(self._summary, 1)
        status_row.addWidget(self._resume_pending)
        status_row.addWidget(self._clear)

        container = QWidget()
        self._cards_layout = QVBoxLayout(container)
        self._cards_layout.setContentsMargins(0, 0, 6, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addWidget(self._empty)
        self._cards_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)
        layout.addWidget(self._banner)
        layout.addLayout(url_row)
        layout.addLayout(options_row)
        layout.addLayout(profile_row)
        layout.addLayout(status_row)
        layout.addWidget(scroll, 1)

        self._url.returnPressed.connect(self._on_add)
        self._add.clicked.connect(self._on_add)
        self._analyze.clicked.connect(self._on_analyze)
        self._import.clicked.connect(self.import_list)
        self._audio_only.toggled.connect(self._sync_enabled)
        self._clear.clicked.connect(manager.clear_finished)
        self._resume_pending.clicked.connect(manager.resume_pending)
        manager.item_added.connect(self._on_item_added)
        manager.item_removed.connect(self._on_item_removed)
        manager.progress_updated.connect(self._refresh_card)
        manager.status_changed.connect(self._refresh_card)
        manager.status_changed.connect(self._update_summary)
        manager.queue_changed.connect(self._update_summary)
        QGuiApplication.clipboard().dataChanged.connect(self._on_clipboard)
        manager.order_changed.connect(self._sync_order)
        self._profile.currentIndexChanged.connect(self._on_profile_changed)
        self._profile_save.clicked.connect(self._save_profile)
        self._profile_delete.clicked.connect(self._delete_profile)
        self._reload_profiles()
        self.refresh_banner()
        self._sync_enabled()
        self._update_summary()

    def add_urls(self, urls: list[str], *, title: str = "", thumbnail: str = "") -> int:
        """Encola URLs con las opciones rápidas actuales; devuelve cuántas se añadieron."""
        if not urls:
            return 0
        if find_ytdlp() is None:
            QMessageBox.critical(
                self,
                "yt-dlp no encontrado",
                "Instala yt-dlp con «pip install yt-dlp» y reinicia la aplicación.",
            )
            return 0
        free = free_space(Path(self._settings.download_path).expanduser())
        if free is not None and free < MIN_FREE_BYTES:
            answer = QMessageBox.question(
                self,
                "Poco espacio en disco",
                f"Solo quedan {format_size(free)} libres en la carpeta de descargas. ¿Continuar de todos modos?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return 0
        self._store_quick_options()
        full_playlists: set[str] = set()
        playlists = [u for u in urls if is_playlist_url(u)]
        if playlists and not self._playlist.isChecked():
            choice = self._ask_playlist(single=len(urls) == 1)
            if choice == "choose":
                self.analyze_requested.emit(playlists[0], True)
                return 0
            if choice != "all":
                return 0
            full_playlists = set(playlists)
        for url in urls:
            options = self._settings.download_options()
            options.update(self._profile_extra)
            if url in full_playlists:
                options["download_playlist"] = True
            self._manager.add(url, options, title=title, thumbnail=thumbnail)
        return len(urls)

    def _ask_playlist(self, *, single: bool) -> str:
        """Pregunta qué hacer con una URL de playlist: 'all', 'choose' o 'cancel'."""
        box = QMessageBox(self)
        box.setWindowTitle("Playlist detectada")
        box.setText("Esta URL es una playlist y «Playlist completa» está desactivado.\n¿Qué quieres hacer?")
        whole = box.addButton("Playlist completa", QMessageBox.ButtonRole.AcceptRole)
        choose = box.addButton("Elegir elementos…", QMessageBox.ButtonRole.ActionRole) if single else None
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == whole:
            return "all"
        if choose is not None and clicked == choose:
            return "choose"
        return "cancel"

    def refresh_banner(self) -> None:
        """Muestra qué herramientas faltan (o se oculta si no falta ninguna)."""
        missing = []
        if find_ytdlp() is None:
            missing.append("yt-dlp (imprescindible)")
        if not check_ffmpeg():
            missing.append("FFmpeg (sin él: un solo archivo, calidad limitada y sin conversión de audio)")
        if find_js_runtime() is None:
            missing.append("Deno (sin él, YouTube puede fallar)")
        self._banner_label.setText("Faltan herramientas: " + "; ".join(missing) + "." if missing else "")
        self._banner.setVisible(bool(missing))

    def _sync_order(self) -> None:
        """Reordena las tarjetas según el orden de la cola."""
        for card in self._cards.values():
            self._cards_layout.removeWidget(card)
        for item_id in self._manager.items:
            card = self._cards.get(item_id)
            if card is not None:
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    _PROFILE_VISIBLE = ("quality", "video_format", "audio_only", "audio_format", "download_playlist")

    def _reload_profiles(self, select: str | None = None) -> None:
        self._profile.blockSignals(True)
        self._profile.clear()
        self._profile.addItem("Sin perfil", None)
        for name in profiles.all_profiles(self._settings):
            self._profile.addItem(name, name)
        index = self._profile.findData(select) if select else 0
        self._profile.setCurrentIndex(max(index, 0))
        self._profile.blockSignals(False)
        self._on_profile_changed()

    def _on_profile_changed(self) -> None:
        name = self._profile.currentData()
        values = profiles.all_profiles(self._settings).get(name, {}) if name else {}
        self._profile_delete.setEnabled(bool(name) and name in self._settings.profiles)
        self._profile_extra = {k: v for k, v in values.items() if k not in self._PROFILE_VISIBLE}
        if "quality" in values:
            self._quality.setCurrentText(values["quality"])
        if "video_format" in values:
            self._video_format.setCurrentText(values["video_format"])
        if "audio_format" in values:
            self._audio_format.setCurrentText(values["audio_format"])
        if "audio_only" in values:
            self._audio_only.setChecked(bool(values["audio_only"]))
        if "download_playlist" in values:
            self._playlist.setChecked(bool(values["download_playlist"]))

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Guardar perfil", "Nombre del perfil:")
        name = name.strip()[:40]
        if not ok or not name:
            return
        if name in profiles.BUILTIN_PROFILES:
            QMessageBox.warning(self, "Nombre reservado", "Ese nombre pertenece a un perfil predefinido.")
            return
        self._store_quick_options()
        snapshot = profiles.snapshot(self._settings)
        snapshot.update(self._profile_extra)
        self._settings.profiles[name] = snapshot
        try:
            self._settings.save()
        except OSError:
            log.exception("No se pudo guardar el perfil")
        self._reload_profiles(select=name)

    def _delete_profile(self) -> None:
        name = self._profile.currentData()
        if name and name in self._settings.profiles:
            del self._settings.profiles[name]
            try:
                self._settings.save()
            except OSError:
                log.exception("No se pudo guardar la configuración")
            self._reload_profiles()

    def _store_quick_options(self) -> None:
        s = self._settings
        s.quality = self._quality.currentText()
        s.video_format = self._video_format.currentText()
        s.audio_only = self._audio_only.isChecked()
        s.audio_format = self._audio_format.currentText()
        s.download_playlist = self._playlist.isChecked()
        try:
            s.save()
        except OSError:
            log.exception("No se pudo guardar la configuración")

    def _sync_enabled(self) -> None:
        audio = self._audio_only.isChecked()
        self._quality.setEnabled(not audio)
        self._video_format.setEnabled(not audio)
        self._audio_format.setEnabled(audio)

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        return [token for token in re.split(r"[\s,]+", text.strip()) if validate_url(token)]

    def _on_add(self) -> None:
        urls = self._extract_urls(self._url.text())
        if not urls:
            QMessageBox.warning(self, "URL no válida", "Introduce una URL http(s) completa.")
            return
        if self.add_urls(urls):
            self._url.clear()

    def _on_analyze(self) -> None:
        urls = self._extract_urls(self._url.text())
        if not urls:
            QMessageBox.warning(self, "URL no válida", "Introduce una URL http(s) completa.")
            return
        self._store_quick_options()
        self.analyze_requested.emit(urls[0], self._playlist.isChecked())

    def paste_and_add(self) -> None:
        """Añade las URLs que haya en el portapapeles."""
        urls = self._extract_urls(QGuiApplication.clipboard().text())
        if not urls:
            self.status_message.emit("El portapapeles no contiene ninguna URL válida")
            return
        added = self.add_urls(urls)
        if added:
            self.status_message.emit(f"{added} URL(s) añadida(s) desde el portapapeles")

    def import_list(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Importar lista de URLs", "", "Texto (*.txt);;Todos (*)")
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo leer el archivo", str(exc))
            return
        added = self.add_urls(self._extract_urls(text))
        self.status_message.emit(f"{added} URLs añadidas desde la lista")

    def _on_clipboard(self) -> None:
        if not self._settings.monitor_clipboard or self._url.text():
            return
        text = QGuiApplication.clipboard().text().strip()
        if validate_url(text):
            self._url.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        texts = [u.toString() for u in mime.urls()] if mime.hasUrls() else mime.text().split()
        urls = [t for t in texts if validate_url(t)]
        if urls:
            event.acceptProposedAction()
            self.add_urls(urls)

    def _on_item_added(self, item_id: str) -> None:
        card = DownloadCard(self._manager.items[item_id], self._manager, self._loader)
        self._cards[item_id] = card
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
        self._empty.setVisible(False)

    def _on_item_removed(self, item_id: str) -> None:
        card = self._cards.pop(item_id, None)
        if card is not None:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._empty.setVisible(not self._cards)
        self._update_summary()

    def _refresh_card(self, item_id: str) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.refresh()

    def _update_summary(self) -> None:
        m = self._manager
        parts = []
        if m.active:
            parts.append(f"{len(m.active)} activas")
        if m.paused:
            parts.append(f"{len(m.paused)} en pausa")
        if m.queue:
            parts.append(f"{len(m.queue)} en cola")
        pending = sum(1 for i in m.items.values() if i.status is Status.PENDING)
        if pending:
            parts.append(f"{pending} pendientes")
        self._resume_pending.setVisible(pending > 0)
        self._summary.setText(" · ".join(parts))
        self._clear.setEnabled(any(i.finished for i in m.items.values()))
