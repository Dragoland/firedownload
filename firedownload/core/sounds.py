"""Sonidos de aviso multiplataforma; si no hay reproductor, se omiten en silencio."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_FREEDESKTOP = Path("/usr/share/sounds/freedesktop/stereo")
_ALSA_FALLBACK = Path("/usr/share/sounds/alsa/Front_Center.wav")
_MACOS = Path("/System/Library/Sounds")


def _linux_command(complete: bool) -> list[str] | None:
    """Primer reproductor disponible: paplay → canberra-gtk-play → aplay."""
    event, sound = ("complete", "complete.oga") if complete else ("dialog-error", "dialog-error.oga")
    if shutil.which("paplay") and (_FREEDESKTOP / sound).is_file():
        return ["paplay", str(_FREEDESKTOP / sound)]
    if shutil.which("canberra-gtk-play"):
        return ["canberra-gtk-play", "-i", event]
    if shutil.which("aplay") and _ALSA_FALLBACK.is_file():
        return ["aplay", "-q", str(_ALSA_FALLBACK)]
    return None


def _play(complete: bool) -> None:
    try:
        if sys.platform == "win32":
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK if complete else winsound.MB_ICONHAND)
            return
        if sys.platform == "darwin":
            sound = _MACOS / ("Glass.aiff" if complete else "Basso.aiff")
            command = ["afplay", str(sound)] if shutil.which("afplay") and sound.is_file() else None
        else:
            command = _linux_command(complete)
        if command:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, RuntimeError) as exc:
        log.debug("No se pudo reproducir el sonido: %s", exc)


def play_complete() -> None:
    """Sonido de descarga completada."""
    _play(True)


def play_error() -> None:
    """Sonido de descarga fallida."""
    _play(False)
