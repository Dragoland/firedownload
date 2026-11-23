"""Diálogo «Acerca de»: programa, componentes, créditos y sección sobre el autor."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtCore import Qt, qVersion
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from firedownload import __author__, __contact__, __copyright__, __github__, __site_web__, __version__
from firedownload.config import Paths, Settings
from firedownload.core.tasks import YtdlpTask
from firedownload.core.utils import external_url, find_ffmpeg, find_js_runtime, find_logo, open_in_file_manager
from firedownload.core.ytdlp import ytdlp_command
from firedownload.ui.check_dialog import CheckDialog

_CREDITS = (
    'Construido sobre <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a> (Unlicense), '
    '<a href="https://doc.qt.io/qtforpython-6/">PySide6 / Qt</a> (LGPLv3) y '
    '<a href="https://github.com/giampaolo/psutil">psutil</a> (BSD-3). '
    '<a href="https://ffmpeg.org">FFmpeg</a> y <a href="https://deno.com">Deno</a> son proyectos independientes que la app puede instalar a petición tuya. '
    'FireDownload se distribuye bajo licencia MIT.'
)
_LEGAL = (
    "Descarga únicamente contenido sobre el que tengas derechos o permiso. "
    "Respeta los términos de cada plataforma y la legislación de tu país."
)
_BRAND = "BitCriollo — Soluciones Digitales con Sabor"
_AUTHOR_BIO = (
    f"{__author__} es el autor de FireDownload y desarrolla bajo la marca BitCriollo, "
    "un proyecto de servicios informáticos desde Falcón, Placetas (Cuba). "
    "Trabaja con Linux, limpieza de virus, recuperación de datos, reparación de PCs "
    "y desarrollo de software a distancia, con diagnóstico gratuito."
)


def _rich(text: str) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setWordWrap(True)
    return label


class AboutDialog(QDialog):
    """Información de la aplicación y de su autor, con opción de copiarla para soporte."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Acerca de FireDownload")
        self.setMinimumWidth(620)
        self._tasks: list[YtdlpTask] = []
        self._values: dict[str, QLabel] = {}

        header = QHBoxLayout()
        header.setSpacing(18)
        logo_path = find_logo()
        if logo_path is not None:
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo = QLabel()
                logo.setPixmap(pixmap.scaledToHeight(96, Qt.TransformationMode.SmoothTransformation))
                header.addWidget(logo)
        titles = QVBoxLayout()
        name = QLabel("FireDownload")
        name.setObjectName("aboutTitle")
        version = QLabel(f"Versión {__version__}")
        version.setObjectName("muted")
        tagline = QLabel("Gestor de descargas de vídeo y audio basado en yt-dlp.")
        tagline.setWordWrap(True)
        for label in (name, version, tagline):
            titles.addWidget(label)
        titles.addStretch(1)
        header.addLayout(titles, 1)

        tabs = QTabWidget()
        tabs.addTab(self._build_program_tab(), "Programa")
        tabs.addTab(self._build_author_tab(), "Sobre el autor")

        copy = QPushButton("Copiar información")
        check = QPushButton("Comprobar instalación…")
        folder = QPushButton("Abrir carpeta de datos")
        close = QPushButton("Cerrar")
        close.setObjectName("primary")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.info_text()))
        check.clicked.connect(self._open_check)
        folder.clicked.connect(lambda: open_in_file_manager(Path(Paths.BASE)))
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        for button in (copy, check, folder):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(tabs, 1)
        layout.addWidget(self._copyright_label())
        layout.addLayout(buttons)

        self._start_probe(ytdlp_command(["--version"]), self._on_ytdlp, self._on_ytdlp_failed, "yt-dlp")
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            self._start_probe([ffmpeg, "-version"], self._on_ffmpeg, self._on_ffmpeg_failed, "FFmpeg")

    def _build_program_tab(self) -> QWidget:
        components = QGroupBox("Componentes")
        form = QFormLayout(components)
        runtime = find_js_runtime()
        rows = {
            "Python": sys.version.split()[0],
            "Qt": f"PySide6 · Qt {qVersion()}",
            "Sistema": platform.platform(),
            "yt-dlp": "comprobando…",
            "FFmpeg": "comprobando…" if find_ffmpeg() else "no encontrado",
            "JavaScript": f"{runtime[0]} ({runtime[1]})" if runtime else "no encontrado (YouTube necesita Deno o Node 20+)",
            "Datos": str(Paths.BASE),
        }
        for key, value in rows.items():
            label = QLabel(value)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._values[key] = label
            form.addRow(key, label)

        legal = QLabel(_LEGAL)
        legal.setObjectName("muted")
        legal.setWordWrap(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(components)
        layout.addWidget(_rich(_CREDITS))
        layout.addWidget(legal)
        layout.addStretch(1)
        return page

    def _build_author_tab(self) -> QWidget:
        name = QLabel(__author__)
        name.setObjectName("title")
        brand = QLabel(_BRAND)
        brand.setObjectName("muted")
        links = _rich(
            f'Web: <a href="{external_url(__site_web__)}">{__site_web__}</a><br>'
            f'GitHub: <a href="{external_url(__github__)}">{__github__}</a><br>'
            f'Correo: <a href="mailto:{__contact__}">{__contact__}</a>'
        )
        support = QLabel(
            "¿Encontraste un error o tienes una idea? Escríbeme o abre una incidencia en GitHub; "
            "«Copiar información» te ayuda a adjuntar los datos de tu equipo."
        )
        support.setObjectName("muted")
        support.setWordWrap(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(name)
        layout.addWidget(brand)
        layout.addWidget(_rich(_AUTHOR_BIO))
        layout.addWidget(links)
        layout.addWidget(support)
        layout.addStretch(1)
        return page

    def _copyright_label(self) -> QLabel:
        return _rich(
            f'{__copyright__} · Licencia MIT · Creado por {__author__} · '
            f'<a href="{external_url(__github__)}">{__github__}</a>'
        )

    def _start_probe(self, command: list[str] | None, on_ok, on_fail, key: str) -> None:  # noqa: ANN001
        if command is None:
            self._values[key].setText("no encontrado")
            return
        task = YtdlpTask(command, 15)
        task.succeeded.connect(on_ok)
        task.failed.connect(on_fail)
        self._tasks.append(task)
        task.start()

    def _on_ytdlp(self, output: str) -> None:
        self._values["yt-dlp"].setText(output.strip() or "instalado")

    def _on_ytdlp_failed(self, _message: str) -> None:
        self._values["yt-dlp"].setText("versión desconocida")

    def _on_ffmpeg(self, output: str) -> None:
        self._values["FFmpeg"].setText(output.splitlines()[0] if output.strip() else "instalado")

    def _on_ffmpeg_failed(self, _message: str) -> None:
        self._values["FFmpeg"].setText("versión desconocida")

    def info_text(self) -> str:
        """Texto plano para adjuntar a un informe de error."""
        lines = [f"FireDownload {__version__} ({__copyright__})", f"Código: {__github__}", f"Web: {__site_web__}"]
        lines += [f"{key}: {label.text()}" for key, label in self._values.items()]
        return "\n".join(lines)

    def _open_check(self) -> None:
        CheckDialog(self._settings, self).exec()

    def done(self, result: int) -> None:
        for task in self._tasks:
            if task.isRunning():
                task.requestInterruption()
        super().done(result)
