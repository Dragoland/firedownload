"""Tareas puntuales de yt-dlp (metadatos, búsqueda, versión, actualización) en un hilo."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from firedownload.core.ytdlp import humanize_error

_ACTIVE: set[YtdlpTask] = set()


def _last_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR:")]
    return (errors or lines or [""])[-1]


class YtdlpTask(QThread):
    """Ejecuta un comando, captura su salida y la emite. Se puede interrumpir."""

    succeeded = Signal(str)
    failed = Signal(str)
    completed = Signal(int, str)

    def __init__(self, command: list[str], timeout: float = 90.0, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._command = command
        self._timeout = timeout
        self.finished.connect(self._release)

    def start(self) -> None:
        _ACTIVE.add(self)
        super().start()

    def _release(self) -> None:
        self.wait()
        _ACTIVE.discard(self)

    def run(self) -> None:
        extra: dict[str, Any] = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            proc = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                **extra,
            )
        except OSError as exc:
            self.failed.emit(f"No se pudo ejecutar el comando: {exc}")
            return

        deadline = time.monotonic() + self._timeout
        while True:
            if self.isInterruptionRequested():
                proc.kill()
                proc.communicate()
                return
            try:
                out, err = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() > deadline:
                    proc.kill()
                    proc.communicate()
                    self.failed.emit("Tiempo de espera agotado.")
                    return

        self.completed.emit(proc.returncode, out + (("\n" + err) if err else ""))
        if proc.returncode == 0:
            self.succeeded.emit(out)
        else:
            self.failed.emit(humanize_error(_last_error(err or out)))


def shutdown_tasks() -> None:
    """Interrumpe y espera a las tareas en curso (al cerrar la aplicación)."""
    tasks = list(_ACTIVE)
    for task in tasks:
        task.requestInterruption()
    for task in tasks:
        task.wait(3000)
