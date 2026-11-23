"""Visor de metadatos: miniatura, datos, pistas de audio, subtítulos y vista previa."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from firedownload.config import AUDIO_FORMATS, QUALITIES, SPONSORBLOCK_MODES, SUBS_MODES, VIDEO_FORMATS, Settings
from firedownload.core.info import MediaInfo, compress_ranges, info_args, parse_info, stream_args
from firedownload.core.tasks import YtdlpTask
from firedownload.core.thumbs import ThumbnailLoader, cover
from firedownload.core.utils import check_ffmpeg, format_count, format_date, format_duration, parse_timestamp
from firedownload.core.ytdlp import ytdlp_command

try:
    from firedownload.ui.preview_dialog import PreviewDialog
except ImportError:
    PreviewDialog = None  # type: ignore[assignment,misc]

log = logging.getLogger(__name__)

_THUMB_W, _THUMB_H = 320, 180


class InfoDialog(QDialog):
    """Obtiene los metadatos de una URL y deja elegir cómo descargarla."""

    def __init__(
        self,
        url: str,
        settings: Settings,
        loader: ThumbnailLoader,
        *,
        playlist: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detalles del medio")
        self.resize(880, 660)
        self.info: MediaInfo | None = None
        self._url = url
        self._settings = settings
        self._loader = loader
        self._thumb_url = ""
        self._info_task: YtdlpTask | None = None
        self._stream_task: YtdlpTask | None = None
        self._build_ui()
        loader.loaded.connect(self._on_thumbnail)
        self._fetch(playlist)

    def _build_ui(self) -> None:
        s = self._settings
        self._status = QLabel("Obteniendo metadatos…")
        self._status.setObjectName("muted")
        self._status.setWordWrap(True)

        self._thumb = QLabel()
        self._thumb.setObjectName("thumb")
        self._thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview = QPushButton("Vista previa")
        self._preview.setEnabled(False)
        self._preview.setVisible(PreviewDialog is not None)
        self._preview.clicked.connect(self._start_preview)

        self._title = QLabel()
        self._title.setObjectName("title")
        self._title.setWordWrap(True)
        self._meta = QLabel()
        self._meta.setObjectName("muted")
        self._meta.setWordWrap(True)
        self._description = QPlainTextEdit()
        self._description.setReadOnly(True)

        left = QVBoxLayout()
        left.addWidget(self._thumb)
        left.addWidget(self._preview)
        left.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(self._title)
        right.addWidget(self._meta)
        right.addWidget(self._description, 1)
        top = QHBoxLayout()
        top.addLayout(left)
        top.addLayout(right, 1)

        self._quality = QComboBox()
        self._quality.addItems(QUALITIES)
        self._video_format = QComboBox()
        self._video_format.addItems(VIDEO_FORMATS)
        self._video_format.setCurrentText(s.video_format)
        self._audio_only = QCheckBox("Solo audio")
        self._audio_only.setChecked(s.audio_only)
        self._audio_format = QComboBox()
        self._audio_format.addItems(AUDIO_FORMATS)
        self._audio_format.setCurrentText(s.audio_format)
        self._audio_only.toggled.connect(self._sync_enabled)
        format_tab = QWidget()
        form = QFormLayout(format_tab)
        form.addRow("Calidad máxima", self._quality)
        form.addRow("Contenedor de vídeo", self._video_format)
        form.addRow("", self._audio_only)
        form.addRow("Formato de audio", self._audio_format)

        self._audio_list = QListWidget()
        self._audio_hint = QLabel("Marca varias pistas para incluirlas todas (se genera un .mkv).")
        self._audio_hint.setObjectName("muted")
        self._audio_hint.setWordWrap(True)
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        audio_layout.addWidget(self._audio_hint)
        audio_layout.addWidget(self._audio_list, 1)

        self._subs_mode = QComboBox()
        for key, label in SUBS_MODES.items():
            self._subs_mode.addItem(label, key)
        self._subs_mode.setCurrentIndex(max(self._subs_mode.findData(s.subs_mode), 0))
        self._subs_list = QListWidget()
        subs_hint = QLabel("Las marcadas «auto» son subtítulos generados automáticamente.")
        if not check_ffmpeg():
            subs_hint.setText(subs_hint.text() + " Convertir e incrustar requiere FFmpeg.")
        subs_hint.setObjectName("muted")
        subs_hint.setWordWrap(True)
        subs_tab = QWidget()
        subs_layout = QVBoxLayout(subs_tab)
        subs_layout.addWidget(self._subs_mode)
        subs_layout.addWidget(subs_hint)
        subs_layout.addWidget(self._subs_list, 1)

        self._embed_metadata = QCheckBox("Incrustar metadatos (título, artista, fecha…)")
        self._embed_metadata.setChecked(s.embed_metadata)
        self._embed_thumbnail = QCheckBox("Incrustar miniatura como carátula")
        self._embed_thumbnail.setChecked(s.embed_thumbnail)
        self._playlist = QCheckBox("Descargar la playlist completa")
        self._playlist.setChecked(s.download_playlist)
        self._sponsorblock = QComboBox()
        for key, label in SPONSORBLOCK_MODES.items():
            self._sponsorblock.addItem(label, key)
        self._sponsorblock.setCurrentIndex(max(self._sponsorblock.findData(s.sponsorblock), 0))
        extras_tab = QWidget()
        extras = QVBoxLayout(extras_tab)
        for box in (self._embed_metadata, self._embed_thumbnail, self._playlist):
            extras.addWidget(box)
        extras.addWidget(QLabel("SponsorBlock (requiere FFmpeg)"))
        extras.addWidget(self._sponsorblock)
        extras.addStretch(1)

        self._items_list = QListWidget()
        all_button = QPushButton("Marcar todo")
        none_button = QPushButton("Desmarcar todo")
        all_button.clicked.connect(lambda: self._set_all_items(Qt.CheckState.Checked))
        none_button.clicked.connect(lambda: self._set_all_items(Qt.CheckState.Unchecked))
        items_tab = QWidget()
        items_layout = QVBoxLayout(items_tab)
        items_buttons = QHBoxLayout()
        items_buttons.addWidget(all_button)
        items_buttons.addWidget(none_button)
        items_buttons.addStretch(1)
        items_layout.addLayout(items_buttons)
        items_layout.addWidget(self._items_list, 1)

        self._cut_start = QLineEdit()
        self._cut_start.setPlaceholderText("Inicio (p. ej. 1:30)")
        self._cut_end = QLineEdit()
        self._cut_end.setPlaceholderText("Fin (p. ej. 2:45; vacío = hasta el final)")
        self._chapter_list = QListWidget()
        cut_hint = QLabel("Descarga solo un fragmento. Requiere FFmpeg. Puedes combinar un rango con capítulos.")
        cut_hint.setObjectName("muted")
        cut_hint.setWordWrap(True)
        cut_tab = QWidget()
        cut_layout = QVBoxLayout(cut_tab)
        cut_layout.addWidget(cut_hint)
        cut_range = QHBoxLayout()
        cut_range.addWidget(self._cut_start)
        cut_range.addWidget(self._cut_end)
        cut_layout.addLayout(cut_range)
        cut_layout.addWidget(QLabel("Capítulos"))
        cut_layout.addWidget(self._chapter_list, 1)

        self._tabs = QTabWidget()
        self._tabs.addTab(format_tab, "Formato")
        self._tabs.addTab(audio_tab, "Pistas de audio")
        self._tabs.addTab(subs_tab, "Subtítulos")
        self._tabs.addTab(extras_tab, "Extras")
        self._tabs.addTab(items_tab, "Elementos")
        self._tabs.addTab(cut_tab, "Recorte")
        self._tabs.setTabEnabled(4, False)
        self._tabs.setEnabled(False)

        self._download = QPushButton("Descargar")
        self._download.setObjectName("primary")
        self._download.setEnabled(False)
        cancel = QPushButton("Cerrar")
        self._download.clicked.connect(self._on_download)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self._download)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addLayout(top, 1)
        layout.addWidget(self._tabs)
        layout.addLayout(buttons)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        audio = self._audio_only.isChecked()
        self._quality.setEnabled(not audio)
        self._video_format.setEnabled(not audio)
        self._audio_format.setEnabled(audio)

    def _fetch(self, playlist: bool) -> None:
        command = ytdlp_command(info_args(self._url, self._settings.download_options(), playlist=playlist))
        if command is None:
            self._status.setText("yt-dlp no está instalado.")
            return
        self._info_task = YtdlpTask(command)
        self._info_task.succeeded.connect(self._on_info)
        self._info_task.failed.connect(self._on_failed)
        self._info_task.start()

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"No se pudieron obtener los metadatos: {message}")

    def _on_info(self, raw: str) -> None:
        try:
            info = parse_info(raw, self._url)
        except ValueError as exc:
            self._status.setText(f"Respuesta no válida de yt-dlp: {exc}")
            return
        self.info = info
        self._status.hide()
        self._title.setText(info.title)
        parts = [info.uploader]
        if info.is_playlist:
            parts.append(f"Playlist · {info.playlist_count} elementos")
        else:
            parts += [
                format_duration(info.duration),
                format_date(info.upload_date),
                f"{format_count(info.view_count)} visualizaciones" if info.view_count else "",
            ]
            if info.chapters:
                parts.append(f"{info.chapters} capítulos")
            if info.heights:
                parts.append(f"hasta {info.heights[0]}p")
        self._meta.setText(" · ".join(p for p in parts if p))
        self._description.setPlainText(info.description[:3000])
        if info.thumbnail:
            self._thumb_url = info.thumbnail
            self._loader.request(info.thumbnail)
        self._fill_quality(info)
        self._fill_audio(info)
        self._fill_subs(info)
        if info.is_playlist:
            self._fill_items(info)
        self._fill_chapters(info)
        self._tabs.setEnabled(True)
        self._download.setEnabled(True)
        self._preview.setEnabled(not info.is_playlist)

    def _fill_quality(self, info: MediaInfo) -> None:
        items = ["Best", *(f"{h}p" for h in info.heights)] if info.heights else list(QUALITIES)
        self._quality.clear()
        self._quality.addItems(items)
        wanted = self._settings.quality
        self._quality.setCurrentIndex(max(self._quality.findText(wanted), 0))

    def _fill_audio(self, info: MediaInfo) -> None:
        self._audio_list.clear()
        wanted = [w.lower() for w in self._settings.audio_langs]
        for code, note in info.audio_tracks:
            item = QListWidgetItem(f"{code} — {note}" if note else code)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = any(code.lower().startswith(w) for w in wanted)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._audio_list.addItem(item)
        multiple = len(info.audio_tracks) > 1
        self._audio_list.setEnabled(multiple)
        if not multiple:
            self._audio_hint.setText("Este medio solo ofrece una pista de audio.")
        self._tabs.setTabEnabled(1, not info.is_playlist)

    def _fill_subs(self, info: MediaInfo) -> None:
        self._subs_list.clear()
        wanted = set(self._settings.subs_langs)
        for entries, auto in ((info.subtitles, False), (info.auto_captions, True)):
            for code, name in entries:
                label = f"{code} — {name}" if name else code
                item = QListWidgetItem(f"{label} (auto)" if auto else label)
                item.setData(Qt.ItemDataRole.UserRole, (code, auto))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = code in wanted and not (auto and code in {c for c, _ in info.subtitles})
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                self._subs_list.addItem(item)
        has_subs = self._subs_list.count() > 0
        self._subs_list.setEnabled(has_subs)
        self._subs_mode.setEnabled(has_subs)
        self._tabs.setTabEnabled(2, not info.is_playlist)

    def _fill_chapters(self, info: MediaInfo) -> None:
        self._chapter_list.clear()
        for start, end, title in info.chapter_list:
            item = QListWidgetItem(f"{format_duration(start) or '0:00'} – {format_duration(end)}  {title}")
            item.setData(Qt.ItemDataRole.UserRole, (start, end))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._chapter_list.addItem(item)
        self._chapter_list.setEnabled(bool(info.chapter_list))
        self._tabs.setTabEnabled(5, not info.is_playlist)

    @staticmethod
    def _seconds(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def _sections(self) -> list[str]:
        """Rangos «*inicio-fin» (en segundos) según el recorte manual y los capítulos marcados."""
        sections: list[str] = []
        start, end = parse_timestamp(self._cut_start.text()), parse_timestamp(self._cut_end.text())
        if start is not None or end is not None:
            sections.append(f"*{self._seconds(start or 0)}-{'inf' if end is None else self._seconds(end)}")
        for chapter_start, chapter_end in self._checked(self._chapter_list):
            sections.append(f"*{self._seconds(chapter_start)}-{self._seconds(chapter_end)}")
        return sections

    def _fill_items(self, info: MediaInfo) -> None:
        self._items_list.clear()
        for position, title in info.playlist_entries:
            item = QListWidgetItem(f"{position}. {title}")
            item.setData(Qt.ItemDataRole.UserRole, position)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._items_list.addItem(item)
        self._playlist.setChecked(True)
        self._playlist.setEnabled(False)
        self._tabs.setTabEnabled(4, True)
        self._tabs.setCurrentIndex(4)

    def _set_all_items(self, state: Qt.CheckState) -> None:
        for i in range(self._items_list.count()):
            self._items_list.item(i).setCheckState(state)

    def _on_download(self) -> None:
        try:
            start, end = parse_timestamp(self._cut_start.text()), parse_timestamp(self._cut_end.text())
        except ValueError:
            QMessageBox.warning(self, "Recorte no válido", "Escribe los tiempos como 90, 1:30 o 1:02:03.")
            return
        if start is not None and end is not None and end <= start:
            QMessageBox.warning(self, "Recorte no válido", "El fin debe ser posterior al inicio.")
            return
        if self.info is not None and self.info.is_playlist and not self._checked(self._items_list):
            QMessageBox.warning(self, "Sin elementos", "Marca al menos un elemento de la playlist.")
            return
        self.accept()

    def _checked(self, widget: QListWidget) -> list[Any]:
        return [
            widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(widget.count())
            if widget.item(i).checkState() == Qt.CheckState.Checked
        ]

    def options(self) -> dict[str, Any]:
        """Opciones de descarga según lo elegido en el diálogo."""
        o = self._settings.download_options()
        o.update(
            quality=self._quality.currentText(),
            video_format=self._video_format.currentText(),
            audio_only=self._audio_only.isChecked(),
            audio_format=self._audio_format.currentText(),
            embed_metadata=self._embed_metadata.isChecked(),
            embed_thumbnail=self._embed_thumbnail.isChecked(),
            download_playlist=self._playlist.isChecked(),
            sponsorblock=self._sponsorblock.currentData(),
        )
        if self.info is not None and self.info.is_playlist:
            picked_items = self._checked(self._items_list)
            o["download_playlist"] = True
            if len(picked_items) < self._items_list.count():
                o["playlist_items"] = compress_ranges(picked_items)
        if self.info is not None and not self.info.is_playlist:
            try:
                sections = self._sections()
            except ValueError:
                sections = []
            if sections:
                o["sections"] = sections
            o["audio_langs"] = self._checked(self._audio_list) if self._audio_list.isEnabled() else []
            picked = self._checked(self._subs_list)
            o["subs_mode"] = self._subs_mode.currentData() if picked else "none"
            o["subs_langs"] = list(dict.fromkeys(code for code, _ in picked))
            o["subs_auto"] = any(auto for _, auto in picked)
        return o

    def _on_thumbnail(self, url: str, pixmap: QPixmap) -> None:
        if url == self._thumb_url:
            self._thumb.setPixmap(cover(pixmap, _THUMB_W, _THUMB_H))

    def _start_preview(self) -> None:
        command = ytdlp_command(stream_args(self._url, self._settings.download_options()))
        if command is None or PreviewDialog is None:
            return
        self._preview.setEnabled(False)
        self._preview.setText("Cargando…")
        self._stream_task = YtdlpTask(command, 60)
        self._stream_task.succeeded.connect(self._on_stream)
        self._stream_task.failed.connect(self._on_stream_failed)
        self._stream_task.start()

    def _reset_preview_button(self) -> None:
        self._preview.setText("Vista previa")
        self._preview.setEnabled(True)

    def _on_stream_failed(self, message: str) -> None:
        self._reset_preview_button()
        QMessageBox.information(self, "Vista previa no disponible", message)

    def _on_stream(self, output: str) -> None:
        self._reset_preview_button()
        lines = [line.strip() for line in output.splitlines() if line.strip().startswith("http")]
        if len(lines) != 1 or PreviewDialog is None:
            QMessageBox.information(
                self,
                "Vista previa no disponible",
                "Este medio no ofrece un stream único reproducible. Descárgalo para verlo.",
            )
            return
        PreviewDialog(lines[0], self.info.title if self.info else "", self).exec()

    def done(self, result: int) -> None:
        for task in (self._info_task, self._stream_task):
            if task is not None and task.isRunning():
                task.requestInterruption()
        super().done(result)
