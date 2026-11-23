"""Descarga, verificación e instalación de yt-dlp, FFmpeg y Deno desde las fuentes oficiales (sin Qt)."""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from firedownload.config import Paths
from firedownload.core.utils import find_ffmpeg, find_js_runtime, find_ytdlp, portable_tools_dir

log = logging.getLogger(__name__)

TOOL_NAMES = ("yt-dlp", "ffmpeg", "deno")
_YTDLP_BASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
_DENO_BASE = "https://github.com/denoland/deno/releases/latest/download/"
_FFMPEG_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"

ProgressFn = Callable[[int, int], None]
CancelFn = Callable[[], bool]


class ToolError(Exception):
    """Fallo al obtener o instalar una herramienta (el mensaje es apto para el usuario)."""


class ToolCancelled(ToolError):
    """El usuario canceló la instalación."""


@dataclass(frozen=True)
class ToolSpec:
    """Qué descargar, cómo verificarlo y qué ejecutables extraer."""

    name: str
    url: str
    checksum_url: str
    asset: str
    archive: str = ""  # "", "zip" o "tar.xz"
    members: tuple[str, ...] = ()  # ejecutables (sin .exe) que se instalan


def _machine(raw: str | None = None) -> str:
    machine = (raw or platform.machine()).lower()
    if machine in ("amd64", "x86_64", "x64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "aarch64"
    if machine in ("armv7l", "armv7"):
        return "armv7l"
    if machine in ("i386", "i686", "x86"):
        return "x86"
    return machine


def _system(system: str | None) -> str:
    system = (system or sys.platform).lower()
    if system.startswith("win"):
        return "windows"
    if system.startswith("darwin") or system == "macos":
        return "darwin"
    return "linux"


_YTDLP_ASSETS = {
    ("windows", "x86_64"): "yt-dlp.exe",
    ("windows", "aarch64"): "yt-dlp_arm64.exe",
    ("windows", "x86"): "yt-dlp_x86.exe",
    ("linux", "x86_64"): "yt-dlp_linux",
    ("linux", "aarch64"): "yt-dlp_linux_aarch64",
    ("linux", "armv7l"): "yt-dlp_linux_armv7l",
}
_DENO_TARGETS = {
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("windows", "aarch64"): "aarch64-pc-windows-msvc",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("darwin", "aarch64"): "aarch64-apple-darwin",
}
_FFMPEG_ASSETS = {
    ("windows", "x86_64"): ("ffmpeg-master-latest-win64-gpl.zip", "zip"),
    ("windows", "aarch64"): ("ffmpeg-master-latest-winarm64-gpl.zip", "zip"),
    ("linux", "x86_64"): ("ffmpeg-master-latest-linux64-gpl.tar.xz", "tar.xz"),
    ("linux", "aarch64"): ("ffmpeg-master-latest-linuxarm64-gpl.tar.xz", "tar.xz"),
}


def spec_for(name: str, system: str | None = None, machine: str | None = None) -> ToolSpec | None:
    """Especificación de descarga para esta plataforma (None si no hay descarga oficial)."""
    key = (_system(system), _machine(machine))
    if name == "yt-dlp":
        if key[0] == "darwin":
            asset = "yt-dlp_macos"
        else:
            asset = _YTDLP_ASSETS.get(key, "")
        return ToolSpec(name, _YTDLP_BASE + asset, _YTDLP_BASE + "SHA2-256SUMS", asset, "", ("yt-dlp",)) if asset else None
    if name == "deno":
        target = _DENO_TARGETS.get(key)
        if not target:
            return None
        asset = f"deno-{target}.zip"
        return ToolSpec(name, _DENO_BASE + asset, _DENO_BASE + asset + ".sha256sum", asset, "zip", ("deno",))
    if name == "ffmpeg":
        found = _FFMPEG_ASSETS.get(key)
        if not found:
            return None
        asset, kind = found
        return ToolSpec(name, _FFMPEG_BASE + asset, _FFMPEG_BASE + "checksums.sha256", asset, kind, ("ffmpeg", "ffprobe"))
    return None


def unsupported_reason(name: str) -> str:
    """Mensaje para plataformas sin descarga automática."""
    if name == "ffmpeg" and _system(None) == "darwin":
        return "En macOS instala FFmpeg con Homebrew: brew install ffmpeg"
    return "No hay una descarga oficial para este sistema; instálalo con tu gestor de paquetes."


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def _open(url: str):  # noqa: ANN202
    request = urllib.request.Request(url, headers={"User-Agent": "FireDownload"})
    return urllib.request.urlopen(request, timeout=30, context=_ssl_context() if url.startswith("https") else None)


def _is_hash(token: str) -> bool:
    return len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token)


def expected_hash(text: str, asset: str) -> str | None:
    """Busca el SHA-256 de `asset` en un archivo de sumas (formato `hash  nombre` o solo el hash)."""
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*").split("/")[-1] == asset and _is_hash(parts[0]):
            return parts[0].lower()
    if len(lines) == 1 and len(lines[0].split()) == 1 and _is_hash(lines[0].strip()):
        return lines[0].strip().lower()
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, progress: ProgressFn | None, cancelled: CancelFn | None) -> None:
    with _open(url) as response, target.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise ToolCancelled("Instalación cancelada.")
            chunk = response.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def _verify(spec: ToolSpec, path: Path) -> None:
    try:
        with _open(spec.checksum_url) as response:
            text = response.read(2_000_000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError(f"No se pudo obtener la suma de verificación: {exc}") from exc
    expected = expected_hash(text, spec.asset)
    if expected is None:
        raise ToolError("La suma de verificación no incluye este archivo; se cancela por seguridad.")
    if _sha256(path) != expected:
        raise ToolError("La descarga no coincide con su suma SHA-256; se descartó por seguridad.")


def _extract(archive: Path, kind: str, members: tuple[str, ...], tmp: Path) -> list[Path]:
    """Extrae solo los ejecutables pedidos, usando únicamente el nombre base (sin rutas del archivo)."""
    suffix = ".exe" if sys.platform == "win32" else ""
    wanted = {f"{m}{suffix}" for m in members}
    found: dict[str, Path] = {}

    def save(name: str, source) -> None:  # noqa: ANN001
        out = tmp / name
        with out.open("wb") as handle:
            shutil.copyfileobj(source, handle)
        found[name] = out

    if kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                name = Path(info.filename).name
                if not info.is_dir() and name in wanted and name not in found:
                    with zf.open(info) as source:
                        save(name, source)
    else:
        with tarfile.open(archive, "r:xz") as tf:
            for member in tf:
                name = Path(member.name).name
                if member.isfile() and name in wanted and name not in found:
                    source = tf.extractfile(member)
                    if source is not None:
                        save(name, source)
    missing = wanted - found.keys()
    if missing:
        raise ToolError(f"El archivo descargado no contiene: {', '.join(sorted(missing))}")
    return list(found.values())


def install(
    spec: ToolSpec,
    *,
    dest_dir: Path | None = None,
    progress: ProgressFn | None = None,
    cancelled: CancelFn | None = None,
) -> list[Path]:
    """Descarga, verifica (SHA-256) e instala una herramienta; devuelve los ejecutables instalados."""
    dest = dest_dir or Paths.BIN
    suffix = ".exe" if sys.platform == "win32" else ""
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".fd-", dir=dest) as tmp_name:
            tmp = Path(tmp_name)
            asset = tmp / "asset.download"
            _download(spec.url, asset, progress, cancelled)
            _verify(spec, asset)
            if spec.archive:
                staged = _extract(asset, spec.archive, spec.members, tmp)
            else:
                single = tmp / f"{spec.members[0]}{suffix}"
                asset.replace(single)
                staged = [single]
            installed: list[Path] = []
            for file in staged:
                if sys.platform != "win32":
                    file.chmod(0o755)
                target = dest / file.name
                os.replace(file, target)
                installed.append(target)
            log.info("Instalado %s en %s", spec.name, dest)
            return installed
    except ToolError:
        raise
    except PermissionError as exc:
        raise ToolError("No se pudo reemplazar el archivo (¿está en uso?). Cierra las descargas e inténtalo de nuevo.") from exc
    except (urllib.error.URLError, OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise ToolError(f"No se pudo instalar {spec.name}: {exc}") from exc


def uninstall(name: str) -> None:
    """Borra la copia instalada por la app (no toca la del sistema)."""
    spec = spec_for(name)
    suffix = ".exe" if sys.platform == "win32" else ""
    for member in spec.members if spec else (name,):
        (Paths.BIN / f"{member}{suffix}").unlink(missing_ok=True)


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    origin: str  # "app", "portable", "system", "python" o "none"
    detail: str = ""


def _origin(path: str) -> str:
    resolved = Path(path).resolve()
    for folder, origin in ((Paths.BIN, "app"), (portable_tools_dir(), "portable")):
        try:
            resolved.relative_to(folder.resolve())
            return origin
        except ValueError:
            continue
    return "system"


def status(name: str) -> ToolStatus:
    """Dónde está (o si falta) una herramienta."""
    if name == "yt-dlp":
        command = find_ytdlp()
        if command is None:
            return ToolStatus(name, None, "none")
        if command[1:3] == ("-m", "yt_dlp"):
            return ToolStatus(name, command[0], "python", "módulo de Python")
        return ToolStatus(name, command[0], _origin(command[0]))
    if name == "ffmpeg":
        path = find_ffmpeg()
        return ToolStatus(name, path, _origin(path)) if path else ToolStatus(name, None, "none")
    runtime = find_js_runtime()
    if runtime is None:
        return ToolStatus("deno", None, "none")
    return ToolStatus("deno", runtime[1], _origin(runtime[1]), runtime[0])
