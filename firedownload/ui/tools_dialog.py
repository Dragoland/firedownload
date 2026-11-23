"""Gestor de herramientas externas: instala y actualiza yt-dlp, FFmpeg y Deno desde la propia app."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firedownload.config import Paths
from firedownload.core import tools
from firedownload.core.tasks import ToolInstallTask, YtdlpTask
from firedownload.core.utils import format_size, open_in_file_manager, refresh_tools
from firedownload.core.ytdlp import ytdlp_command

_INFO = {
    "yt-dlp": ("yt-dlp", "Descarga los vídeos y el audio. Imprescindible."),
    "ffmpeg": ("FFmpeg", "Une vídeo y audio, extrae MP3, convierte e incrusta subtítulos, metadatos y miniaturas."),
    "deno": ("Deno", "Runtime de JavaScript que YouTube exige a yt-dlp. Sin él, YouTube puede fallar."),
}
_ORIGINS = {
    "app": "Instalado por FireDownload",
    "portable": "Carpeta tools/ junto a la aplicación",
    "system": "Instalado en el sistema",
    "python": "Módulo de Python",
}


class ToolRow(QFrame):
    """Una herramienta: estado, versión y botones de instalar, actualizar o quitar."""

    changed = Signal()

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._name = name
        self._task: ToolInstallTask | None = None
        self._version_task: YtdlpTask | None = None
        self._version = ""

        title, description = _INFO[name]
        self._title = QLabel(title)
        self._title.setObjectName("title")
        self._desc = QLabel(description)
        self._desc.setObjectName("muted")
        self._desc.setWordWrap(True)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setVisible(False)
        self._action = QPushButton()
        self._remove = QPushButton("Quitar")
        self._remove.setObjectName("danger")

        texts = QVBoxLayout()
        for widget in (self._title, self._desc, self._status, self._bar):
            texts.addWidget(widget)
        buttons = QVBoxLayout()
        buttons.addWidget(self._action)
        buttons.addWidget(self._remove)
        buttons.addStretch(1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addLayout(texts, 1)
        layout.addLayout(buttons)

        self._action.clicked.connect(self._on_action)
        self._remove.clicked.connect(self._on_remove)
        self.refresh()

    @property
    def missing(self) -> bool:
        return tools.status(self._name).path is None

    @property
    def busy(self) -> bool:
        return self._task is not None

    def refresh(self) -> None:
        state = tools.status(self._name)
        if state.path is None:
            self._status.setObjectName("warning")
            self._status.setText("No instalado")
            self._action.setText("Instalar")
        else:
            self._status.setObjectName("muted")
            origin = _ORIGINS.get(state.origin, state.origin)
            extra = f" · {state.detail}" if state.detail and state.detail != "deno" else ""
            version = f" · {self._version}" if self._version else ""
            self._status.setText(f"{origin}{extra}{version}\n{state.path}")
            self._action.setText("Actualizar" if state.origin in ("app", "portable") else "Instalar copia propia")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._remove.setVisible(state.origin == "app" and not self.busy)
        self._action.setEnabled(True)
        if self._name == "yt-dlp" and state.path and not self._version:
            self._probe_version()

    def _probe_version(self) -> None:
        command = ytdlp_command(["--version"])
        if command is None:
            return
        self._version_task = YtdlpTask(command, 20)
        self._version_task.succeeded.connect(self._on_version)
        self._version_task.start()

    def _on_version(self, output: str) -> None:
        self._version = output.strip()
        self.refresh()

    def start(self, *, confirm: bool = True) -> None:
        """Descarga e instala la herramienta."""
        if self._task is not None:
            return
        spec = tools.spec_for(self._name)
        if spec is None:
            QMessageBox.information(self, _INFO[self._name][0], tools.unsupported_reason(self._name))
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                f"Instalar {_INFO[self._name][0]}",
                f"Se descargará «{spec.asset}» desde:\n{spec.url}\n\n"
                "Se verificará su suma SHA-256 antes de instalarlo. ¿Continuar?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._task = ToolInstallTask(spec)
        self._task.progress.connect(self._on_progress)
        self._task.succeeded.connect(self._on_done)
        self._task.failed.connect(self._on_failed)
        self._bar.setRange(0, 0)
        self._bar.setVisible(True)
        self._action.setText("Cancelar")
        self._remove.setVisible(False)
        self._status.setText("Descargando…")
        self._task.start()

    def cancel(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            for signal, slot in (
                (task.progress, self._on_progress),
                (task.succeeded, self._on_done),
                (task.failed, self._on_failed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            task.requestInterruption()
        self._bar.setVisible(False)
        self.refresh()

    def _on_action(self) -> None:
        if self._task is not None:
            self.cancel()
        else:
            self.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._bar.setRange(0, 1000)
            self._bar.setValue(int(done / total * 1000))
            self._status.setText(f"Descargando… {format_size(done)} de {format_size(total)}")
        else:
            self._status.setText(f"Descargando… {format_size(done)}")

    def _on_done(self, _names: str) -> None:
        self._task = None
        self._bar.setVisible(False)
        self._version = ""
        refresh_tools()
        self.refresh()
        self.changed.emit()

    def _on_failed(self, message: str) -> None:
        self._task = None
        self._bar.setVisible(False)
        self.refresh()
        QMessageBox.warning(self, "No se pudo instalar", message)

    def _on_remove(self) -> None:
        answer = QMessageBox.question(self, "Quitar herramienta", "¿Quitar la copia instalada por FireDownload?")
        if answer == QMessageBox.StandardButton.Yes:
            tools.uninstall(self._name)
            self._version = ""
            refresh_tools()
            self.refresh()
            self.changed.emit()


class ToolsDialog(QDialog):
    """Ventana con las tres herramientas y un botón para instalar las que falten."""

    tools_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Herramientas")
        self.resize(720, 560)
        intro = QLabel(
            "FireDownload puede instalar por ti lo que necesita. Las herramientas se guardan en "
            f"{Paths.BIN} y se verifican con SHA-256 antes de instalarse."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        self._rows = [ToolRow(name) for name in tools.TOOL_NAMES]
        for row in self._rows:
            row.changed.connect(self._on_row_changed)

        install_all = QPushButton("Instalar todo lo que falta")
        install_all.setObjectName("primary")
        folder = QPushButton("Abrir carpeta")
        close = QPushButton("Cerrar")
        install_all.clicked.connect(self._install_missing)
        folder.clicked.connect(lambda: open_in_file_manager(Paths.BIN))
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(install_all)
        buttons.addWidget(folder)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(intro)
        for row in self._rows:
            layout.addWidget(row)
        layout.addStretch(1)
        layout.addLayout(buttons)

    def _on_row_changed(self) -> None:
        self.tools_changed.emit()

    def _install_missing(self) -> None:
        missing = [row for row in self._rows if row.missing and not row.busy]
        if not missing:
            QMessageBox.information(self, "Herramientas", "No falta ninguna herramienta.")
            return
        names = ", ".join(_INFO[row._name][0] for row in missing)
        answer = QMessageBox.question(
            self,
            "Instalar herramientas",
            f"Se descargarán e instalarán: {names}.\nSe verificará la suma SHA-256 de cada descarga. ¿Continuar?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            for row in missing:
                row.start(confirm=False)

    def done(self, result: int) -> None:
        for row in self._rows:
            if row.busy:
                row.cancel()
        super().done(result)
