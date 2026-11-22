"""Utilidades sin dependencias de Qt."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)


def validate_url(url: str) -> bool:
    """True si es una URL http(s) con un host razonable."""
    url = url.strip()
    if not url or any(ch.isspace() for ch in url):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and "." in (parsed.hostname or "")


@lru_cache(maxsize=1)
def find_ytdlp() -> tuple[str, ...] | None:
    """Comando base para lanzar yt-dlp, o None si no está disponible."""
    if not getattr(sys, "frozen", False) and importlib.util.find_spec("yt_dlp"):
        return (sys.executable, "-m", "yt_dlp")
    exe = shutil.which("yt-dlp")
    return (exe,) if exe else None


_JS_RUNTIMES: tuple[tuple[str, str], ...] = (("deno", "deno"), ("node", "node"), ("quickjs", "qjs"))


def _node_is_recent(path: str) -> bool:
    """yt-dlp exige Node 20 o superior."""
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        return int(result.stdout.strip().lstrip("v").split(".")[0]) >= 20
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


@lru_cache(maxsize=1)
def find_js_runtime() -> tuple[str, str] | None:
    """Runtime de JavaScript que yt-dlp necesita para YouTube: (nombre, ruta) o None."""
    for name, executable in _JS_RUNTIMES:
        found = shutil.which(executable)
        if not found and name == "deno":
            candidate = Path.home() / ".deno" / "bin" / ("deno.exe" if sys.platform == "win32" else "deno")
            found = str(candidate) if candidate.is_file() else None
        if found and (name != "node" or _node_is_recent(found)):
            return name, found
    return None


def is_playlist_url(url: str) -> bool:
    """True si es una URL de playlist de YouTube sin vídeo concreto."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        return False
    query = parse_qs(parsed.query)
    return "list" in query and "v" not in query


def read_tail(path: Path, lines: int = 300) -> str:
    """Últimas líneas de un archivo de texto (vacío si no existe)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def check_ffmpeg() -> bool:
    """True si ffmpeg está en el PATH."""
    return shutil.which("ffmpeg") is not None


def open_in_file_manager(path: Path) -> bool:
    """Abre el gestor de archivos, seleccionando el fichero si existe."""
    try:
        target = path
        if path.is_file():
            if sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{path}"])
                return True
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
                return True
            target = path.parent
        elif not path.is_dir():
            target = path.parent
        if not target.is_dir():
            return False
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(
                ["xdg-open", str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except OSError as exc:
        log.warning("No se pudo abrir %s: %s", path, exc)
        return False


def open_file(path: Path) -> bool:
    """Abre un archivo con la aplicación predeterminada del sistema."""
    if not path.is_file():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except OSError as exc:
        log.warning("No se pudo abrir %s: %s", path, exc)
        return False


def resource_path(relative: str) -> Path:
    """Ruta a un recurso del proyecto, también dentro de un ejecutable PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parents[2]
    return root / relative


def find_logo() -> Path | None:
    """Busca Logo.png en assets/ o en la raíz del proyecto."""
    for relative in ("assets/Logo.png", "Logo.png"):
        path = resource_path(relative)
        if path.is_file():
            return path
    return None


def external_url(value: str) -> str:
    """«github.com/x/y» → «https://github.com/x/y» (respeta http/https/mailto si ya vienen)."""
    value = value.strip()
    return value if value.startswith(("http://", "https://", "mailto:")) else f"https://{value}"


def format_duration(seconds: float | None) -> str:
    """90 → «1:30»; 3700 → «1:01:40»."""
    if not seconds:
        return ""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_date(raw: str | None) -> str:
    """«20240131» → «2024-01-31»."""
    if raw and len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw or ""


def format_count(number: int | None) -> str:
    """1_234_567 → «1.2M»."""
    if number is None:
        return ""
    value = float(number)
    for suffix in ("", "K", "M", "B"):
        if value < 1000:
            return f"{value:.0f}{suffix}" if suffix == "" else f"{value:.1f}{suffix}"
        value /= 1000
    return f"{value:.1f}T"


_SPEED_RE = re.compile(r"([\d.]+)\s*([KMGT]?i?B)/s", re.IGNORECASE)
_UNITS = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "TIB": 1024**4, "KB": 1000, "MB": 1000**2, "GB": 1000**3}


def parse_speed(text: str) -> float:
    """«1.5MiB/s» → bytes por segundo (0 si no se reconoce, p. ej. «Unknown B/s»)."""
    match = _SPEED_RE.search(text or "")
    if not match:
        return 0.0
    try:
        return float(match.group(1)) * _UNITS.get(match.group(2).upper(), 0)
    except ValueError:
        return 0.0


def format_size(num: float) -> str:
    """1536 → «1.5 KiB»."""
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def format_speed(bytes_per_second: float) -> str:
    return f"{format_size(bytes_per_second)}/s"


def free_space(path: Path) -> int | None:
    """Bytes libres en el disco de `path` (usa el ancestro existente más cercano)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def read_json(path: Path, default: Any) -> Any:
    """Lee JSON; si está corrupto lo aparta como .bak y devuelve default."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except ValueError as exc:
        log.warning("JSON corrupto en %s: %s", path, exc)
        try:
            path.replace(path.with_suffix(path.suffix + ".bak"))
        except OSError:
            pass
        return default
    except OSError as exc:
        log.warning("No se pudo leer %s: %s", path, exc)
        return default


def write_json(path: Path, data: Any) -> None:
    """Escribe JSON de forma atómica (puede lanzar OSError)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
