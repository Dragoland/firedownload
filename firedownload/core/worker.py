"""Hilo de descarga: ejecuta yt-dlp como subproceso con pausa real."""

from __future__ import annotations

import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Mapping
from typing import Any

import psutil
from PySide6.QtCore import QObject, QThread, Signal

from firedownload.core.utils import check_ffmpeg, find_ytdlp
from firedownload.core.ytdlp import build_args, humanize_error, js_runtime_args

log = logging.getLogger(__name__)

_PROGRESS_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*[\d.]+\s*\w+"
    r"(?:\s+at\s+(\S+/s|Unknown B/s))?"
    r"(?:\s+ETA\s+(\S+))?"
)
_PATH_RES = (
    re.compile(r"\[download\]\s+Destination:\s+(.+)"),
    re.compile(r"\[ExtractAudio\]\s+Destination:\s+(.+)"),
    re.compile(r'\[Merger\]\s+Merging formats into "(.+)"'),
    re.compile(r"\[download\]\s+(.+?)\s+has already been downloaded"),
)
_PHASES: tuple[tuple[str, str], ...] = (
    ("[Merger]", "Uniendo vídeo y audio…"),
    ("[ExtractAudio]", "Extrayendo audio…"),
    ("[Metadata]", "Añadiendo metadatos…"),
    ("[EmbedThumbnail]", "Incrustando miniatura…"),
    ("[EmbedSubtitle]", "Incrustando subtítulos…"),
    ("[SubtitlesConvertor]", "Convirtiendo subtítulos…"),
    ("[VideoConvertor]", "Convirtiendo…"),
    ("[VideoRemuxer]", "Convirtiendo…"),
    ("[MoveFiles]", "Moviendo archivos…"),
)
_ITEM_RE = re.compile(r"\[download\]\s+Downloading (?:item|video) (\d+) of (\d+)")
_STREAM_FILE_RE = re.compile(r"\.f[\w\-=+]+\.\w+$")
_SUBTITLE_RE = re.compile(r"\[info\]\s+Writing video subtitles to:\s+(.+)")
_CONVERTED_RE = re.compile(r"\[SubtitlesConvertor\]")
class DownloadWorker(QThread):
    """Ejecuta yt-dlp en un subproceso y reporta progreso; permite pausar y cancelar."""

    progress = Signal(str, float, str, str)
    destination = Signal(str, str)
    phase = Signal(str, str)
    finished_sig = Signal(str, bool, str, str)

    def __init__(
        self,
        item_id: str,
        url: str,
        options: Mapping[str, Any],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_id = item_id
        self.url = url
        self._options = dict(options)
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()
        self._paused = False
        self._cancelled = False
        self._file_path = ""
        self._sub_path = ""
        self._item_index, self._item_total = 1, 1
        self._streams_seen, self._streams_total = 0, 1
        self._stream_index = 0
        self._tail: deque[str] = deque(maxlen=40)
        self._command_line = ""
        self._seen_progress = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def diagnostics(self) -> str:
        """Comando y últimas líneas de yt-dlp, para copiar en un informe de error."""
        return f"Comando:\n{self._command_line}\n\nSalida (últimas líneas):\n" + "\n".join(self._tail)

    def pause(self) -> None:
        """Suspende yt-dlp y sus procesos hijos (ffmpeg)."""
        with self._lock:
            if self._paused:
                return
            self._paused = True
            self._signal_tree(stop=True)

    def resume(self) -> None:
        """Reanuda un proceso suspendido."""
        with self._lock:
            if not self._paused:
                return
            self._paused = False
            self._signal_tree(stop=False)

    def cancel(self) -> None:
        """Termina el proceso; la señal finished_sig se emite al acabar el hilo."""
        with self._lock:
            self._cancelled = True
            self.resume()
            self._terminate()

    def run(self) -> None:
        command = find_ytdlp()
        if command is None:
            self.finished_sig.emit(
                self.item_id, False, "No se encontró yt-dlp. Instálalo con: pip install yt-dlp", ""
            )
            return

        outcome = self._attempt(command, js=True)
        if outcome is not None and outcome[0] != 0 and js_runtime_args() and self._unsupported_option():
            log.warning("Este yt-dlp no admite las opciones de JavaScript; reintentando sin ellas")
            self._reset_state()
            outcome = self._attempt(command, js=False)
        if outcome is None:
            return
        code, errors = outcome

        subs_only = self._options.get("subs_mode") == "only" and bool(self._options.get("subs_langs"))
        if subs_only:
            result_path = self._sub_path or self._file_path
        else:
            result_path = self._file_path or self._sub_path
        if self._cancelled:
            self.finished_sig.emit(self.item_id, False, "Cancelado", result_path)
        elif code == 0 and result_path:
            self.finished_sig.emit(self.item_id, True, "Completado", result_path)
        elif code == 0:
            self.finished_sig.emit(
                self.item_id, False, "yt-dlp terminó sin descargar ningún archivo. Usa «Copiar detalle» para ver su salida.", ""
            )
        else:
            reason = errors[-1] if errors else f"yt-dlp terminó con código {code}"
            self.finished_sig.emit(self.item_id, False, humanize_error(reason), "")

    def _unsupported_option(self) -> bool:
        return any("no such option" in line.lower() for line in self._tail)

    def _reset_state(self) -> None:
        self._file_path = self._sub_path = ""
        self._item_index, self._item_total = 1, 1
        self._streams_seen, self._streams_total, self._stream_index = 0, 1, 0
        self._seen_progress = False
        self._tail.clear()
        with self._lock:
            self._proc = None

    def _attempt(self, command: tuple[str, ...], *, js: bool) -> tuple[int, list[str]] | None:
        """Lanza yt-dlp una vez. Devuelve (código, errores) o None si ya se informó el final."""
        args = [*command, *build_args(self.url, self._options, ffmpeg=check_ffmpeg(), js=js)]
        self._command_line = shlex.join(args)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        extra: dict[str, Any] = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            extra["start_new_session"] = True

        try:
            with self._lock:
                if self._cancelled:
                    proc = None
                else:
                    proc = subprocess.Popen(
                        args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        env=env,
                        **extra,
                    )
                    self._proc = proc
                    if self._paused:
                        self._signal_tree(stop=True)
        except OSError as exc:
            log.exception("No se pudo lanzar yt-dlp")
            self.finished_sig.emit(self.item_id, False, f"No se pudo lanzar yt-dlp: {exc}", "")
            return None

        if proc is None:
            self.finished_sig.emit(self.item_id, False, "Cancelado", "")
            return None

        errors: list[str] = []
        if proc.stdout is not None:
            for raw in proc.stdout:
                line = raw.strip()
                if line:
                    self._handle_line(line, errors)
            proc.stdout.close()
        return proc.wait(), errors

    def _overall(self, percent: float) -> float:
        """Progreso global: reparte el % entre pistas (vídeo+audio) y elementos de playlist."""
        stream = (self._stream_index + percent / 100) / self._streams_total
        overall = ((self._item_index - 1) + stream) / self._item_total * 100
        return min(max(overall, 0.0), 100.0)

    def _announce_phase(self, line: str) -> None:
        for prefix, text in _PHASES:
            if line.startswith(prefix):
                self.phase.emit(self.item_id, text)
                return
        if not self._seen_progress and line.startswith("[") and not line.startswith(("[download]", "[debug]")):
            self.phase.emit(self.item_id, "Obteniendo información…")

    def _on_destination(self, path: str) -> None:
        if _STREAM_FILE_RE.search(path):
            if self._streams_total == 1 and not self._options.get("audio_only"):
                self._streams_total = 1 + max(1, len(self._options.get("audio_langs") or []))
            self._stream_index = min(self._streams_seen, self._streams_total - 1)
            self._streams_seen += 1
        self._file_path = path
        self.destination.emit(self.item_id, path)

    def _handle_line(self, line: str, errors: list[str]) -> None:
        match = _PROGRESS_RE.search(line)
        if match:
            try:
                percent = float(match.group(1))
            except ValueError:
                return
            self._seen_progress = True
            self.progress.emit(self.item_id, self._overall(percent), match.group(2) or "", match.group(3) or "")
            return
        self._tail.append(line)
        self._announce_phase(line)
        match = _ITEM_RE.search(line)
        if match:
            self._item_index, self._item_total = int(match.group(1)), max(int(match.group(2)), 1)
            self._streams_seen, self._streams_total, self._stream_index = 0, 1, 0
            return
        for pattern in _PATH_RES:
            match = pattern.search(line)
            if match:
                self._on_destination(match.group(1).strip())
                return
        match = _SUBTITLE_RE.search(line)
        if match:
            self._sub_path = match.group(1).strip()
            return
        if _CONVERTED_RE.search(line) and self._sub_path:
            self._sub_path = re.sub(r"\.\w+$", ".srt", self._sub_path)
            return
        if line.startswith("ERROR:"):
            errors.append(line)

    def _tree(self) -> list[psutil.Process]:
        """Proceso de yt-dlp y todos sus descendientes."""
        if self._proc is None or self._proc.poll() is not None:
            return []
        try:
            root = psutil.Process(self._proc.pid)
            return [root, *root.children(recursive=True)]
        except psutil.Error:
            return []

    def _signal_tree(self, *, stop: bool) -> None:
        for proc in self._tree():
            try:
                if sys.platform == "win32":
                    if stop:
                        proc.suspend()
                    else:
                        proc.resume()
                else:
                    proc.send_signal(signal.SIGSTOP if stop else signal.SIGCONT)
            except psutil.Error:
                continue

    def _terminate(self) -> None:
        procs = self._tree()
        for proc in reversed(procs):
            try:
                proc.terminate()
            except psutil.Error:
                continue
        _, alive = psutil.wait_procs(procs, timeout=3)
        for proc in alive:
            try:
                proc.kill()
            except psutil.Error:
                continue
