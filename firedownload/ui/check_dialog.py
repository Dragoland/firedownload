"""Comprobación de la instalación: entorno, yt-dlp en modo verbose y una descarga real mínima."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firedownload import __version__
from firedownload.config import Paths, Settings
from firedownload.core.tasks import YtdlpTask
from firedownload.core.utils import check_ffmpeg, find_js_runtime, find_ytdlp
from firedownload.core.ytdlp import common_args, ytdlp_command

TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IAdw"


class CheckDialog(QDialog):
    """Ejecuta pruebas reales y deja un informe copiable para diagnosticar fallos."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comprobar instalación")
        self.resize(900, 620)
        self._settings = settings
        self._task: YtdlpTask | None = None
        self._workdir = Paths.CACHE / "selftest"

        self._url = QLineEdit(TEST_URL)
        self._run = QPushButton("Ejecutar prueba")
        self._run.setObjectName("primary")
        self._copy = QPushButton("Copiar informe")
        close = QPushButton("Cerrar")
        self._report = QPlainTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        top = QHBoxLayout()
        top.addWidget(self._url, 1)
        top.addWidget(self._run)
        bottom = QHBoxLayout()
        bottom.addWidget(self._copy)
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._report, 1)
        layout.addLayout(bottom)

        self._run.clicked.connect(self._start)
        self._copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._report.toPlainText()))
        close.clicked.connect(self.accept)
        self._environment()

    def _log(self, text: str) -> None:
        self._report.appendPlainText(text)

    def _environment(self) -> None:
        s = self._settings
        try:
            import PySide6

            qt_version = PySide6.__version__
        except (ImportError, AttributeError):
            qt_version = "?"
        runtime = find_js_runtime()
        folder = Path(s.download_path)
        self._report.setPlainText(
            "\n".join(
                [
                    f"FireDownload {__version__}",
                    f"Python {sys.version.split()[0]} · PySide6 {qt_version} · {platform.platform()}",
                    f"yt-dlp: {' '.join(find_ytdlp() or ('NO ENCONTRADO',))}",
                    f"JavaScript: {f'{runtime[0]} ({runtime[1]})' if runtime else 'NO ENCONTRADO (YouTube necesita Deno o Node 20+)'}",
                    f"FFmpeg: {shutil.which('ffmpeg') if check_ffmpeg() else 'NO ENCONTRADO'}",
                    f"Carpeta de descargas: {folder} ({'existe' if folder.is_dir() else 'no existe todavía'})",
                    f"Proxy: {s.proxy or '-'} · Cookies: {s.cookies_browser or '-'}",
                    "",
                ]
            )
        )

    def _start(self) -> None:
        url = self._url.text().strip()
        options = self._settings.download_options()
        command = ytdlp_command(["-v", "--simulate", "--no-playlist", "-f", "bv*+ba/b", *common_args(options), "--", url])
        if command is None:
            self._log("ERROR: yt-dlp no está instalado.")
            return
        self._run.setEnabled(False)
        self._log("\n=== 1/2 Extracción (sin descargar) ===")
        self._launch(command, 120, self._after_extract)

    def _launch(self, command: list[str], timeout: float, handler) -> None:  # noqa: ANN001
        self._task = YtdlpTask(command, timeout)
        self._task.completed.connect(handler)
        self._task.failed.connect(self._on_timeout)
        self._task.start()

    def _on_timeout(self, message: str) -> None:
        if "Tiempo de espera" in message:
            self._log(f"\nERROR: {message}")
            self._run.setEnabled(True)

    def _after_extract(self, code: int, output: str) -> None:
        self._log(output.strip())
        self._log(f"\n→ Resultado: {'OK' if code == 0 else f'FALLÓ (código {code})'}")
        if code != 0:
            self._run.setEnabled(True)
            return
        options = self._settings.download_options()
        self._workdir.mkdir(parents=True, exist_ok=True)
        template = str(self._workdir / "%(id)s.%(ext)s")
        command = ytdlp_command([
            "--newline", "--no-playlist", "-f", "worst[ext=mp4]/worst", "-o", template,
            *common_args(options), "--", self._url.text().strip(),
        ])
        self._log("\n=== 2/2 Descarga real mínima ===")
        if command is None:
            self._run.setEnabled(True)
            return
        self._launch(command, 180, self._after_download)

    def _after_download(self, code: int, output: str) -> None:
        self._log(output.strip())
        files = [p for p in self._workdir.glob("*") if p.is_file()] if self._workdir.is_dir() else []
        if code == 0 and files:
            sizes = ", ".join(f"{p.name} ({p.stat().st_size // 1024} KB)" for p in files)
            self._log(f"\n→ Resultado: OK. Archivos: {sizes}")
        else:
            self._log(f"\n→ Resultado: FALLÓ (código {code}, {len(files)} archivos)")
        shutil.rmtree(self._workdir, ignore_errors=True)
        self._run.setEnabled(True)

    def done(self, result: int) -> None:
        if self._task is not None and self._task.isRunning():
            self._task.requestInterruption()
        super().done(result)
