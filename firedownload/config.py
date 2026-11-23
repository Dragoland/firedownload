"""Rutas, sitios soportados y ajustes de la aplicación."""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from firedownload.core.utils import read_json, write_json

log = logging.getLogger(__name__)


def _app_dir() -> Path:
    """Carpeta de datos de la aplicación según el sistema operativo."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return root / "FireDownload"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FireDownload"
    return Path.home() / ".config" / "firedownload"


class Paths:
    """Rutas fijas de configuración, historial, caché y logs."""

    BASE = _app_dir()
    CACHE = BASE / "cache"
    LOGS = BASE / "logs"
    CONFIG_FILE = BASE / "config.json"
    HISTORY_FILE = BASE / "history.json"
    QUEUE_FILE = BASE / "queue.json"
    ARCHIVE_FILE = BASE / "archive.txt"
    BIN = BASE / "bin"
    LOG_FILE = LOGS / "app.log"

    @classmethod
    def ensure(cls) -> None:
        """Crea las carpetas de la aplicación si no existen."""
        for folder in (cls.BASE, cls.CACHE, cls.LOGS, cls.BIN):
            folder.mkdir(parents=True, exist_ok=True)


class Sites:
    """Plataformas conocidas y detección por dominio."""

    GENERIC = "Generic"
    SUPPORTED: dict[str, list[str]] = {
        "YouTube": ["youtube.com", "youtu.be"],
        "TikTok": ["tiktok.com", "vm.tiktok.com"],
        "Instagram": ["instagram.com"],
        "Twitter": ["twitter.com", "x.com"],
        "Twitch": ["twitch.tv", "clips.twitch.tv"],
        "Reddit": ["reddit.com"],
        "Dailymotion": ["dailymotion.com"],
        "SoundCloud": ["soundcloud.com", "on.soundcloud.com"],
        "Vimeo": ["vimeo.com"],
        "Facebook": ["facebook.com"],
        "LinkedIn": ["linkedin.com"],
        "Rumble": ["rumble.com"],
        "Bilibili": ["bilibili.com"],
        "Odysee": ["odysee.com"],
    }

    @classmethod
    def detect(cls, url: str) -> str:
        """Devuelve el nombre de la plataforma o «Generic»."""
        host = (urlparse(url.strip()).hostname or "").lower().removeprefix("www.")
        for name, domains in cls.SUPPORTED.items():
            if any(host == d or host.endswith("." + d) for d in domains):
                return name
        return cls.GENERIC


QUALITIES: tuple[str, ...] = ("Best", "4K", "1440p", "1080p", "720p", "480p", "360p")
VIDEO_FORMATS: tuple[str, ...] = ("mp4", "mkv", "webm")
AUDIO_FORMATS: tuple[str, ...] = ("mp3", "m4a", "opus", "flac", "wav")
SUBS_MODES: dict[str, str] = {
    "none": "No descargar",
    "files": "Archivos .srt junto al vídeo",
    "embed": "Incrustar en el vídeo",
    "only": "Solo subtítulos (sin vídeo)",
}
COOKIE_BROWSERS: tuple[str, ...] = (
    "brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale",
)
FILENAME_TEMPLATES: tuple[str, ...] = (
    "%(title)s.%(ext)s",
    "%(uploader)s - %(title)s.%(ext)s",
    "%(title)s [%(id)s].%(ext)s",
    "%(playlist_index)s - %(title)s.%(ext)s",
)
SPONSORBLOCK_MODES: dict[str, str] = {
    "off": "No usar SponsorBlock",
    "mark": "Marcar segmentos como capítulos",
    "remove": "Eliminar patrocinios y autopromoción",
}
OVERWRITE_MODES: dict[str, str] = {"skip": "Omitir (no volver a descargar)", "overwrite": "Sobrescribir"}
PROFILE_KEYS = frozenset({
    "quality", "video_format", "audio_format", "audio_only", "download_playlist", "audio_langs",
    "subs_mode", "subs_langs", "subs_auto", "embed_metadata", "embed_thumbnail", "sponsorblock",
})
MAX_PROFILES = 20
SEARCH_SOURCES: dict[str, str] = {"YouTube": "ytsearch", "SoundCloud": "scsearch"}
SEARCH_LIMIT = 20
MAX_CONCURRENT_LIMIT = 5
MAX_RETRIES_LIMIT = 10

SECTION_RE = re.compile(r"^\*\d+(\.\d+)?-(\d+(\.\d+)?|inf)$")
_ITEMS_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")
_QUALITY_RE = re.compile(r"^\d{3,4}p$")
_LANG_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,24}$")
_SPEED_RE = re.compile(r"^\d+(\.\d+)?[KkMm]?$")
_PROXY_RE = re.compile(r"^(https?|socks4a?|socks5h?)://\S+$")


def is_valid_quality(quality: str) -> bool:
    return quality in ("Best", "4K") or bool(_QUALITY_RE.match(quality))


def quality_height(quality: str) -> int | None:
    """Altura máxima en píxeles de una calidad («Best» → None)."""
    if quality == "4K":
        return 2160
    if _QUALITY_RE.match(quality):
        return int(quality[:-1])
    return None


def lang_list(value: Any) -> list[str]:
    """Normaliza «es, en» o ['es', 'en'] a una lista de códigos válidos sin duplicados."""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        code = str(item).strip()
        if _LANG_RE.match(code) and code not in result:
            result.append(code)
    return result


def is_valid_speed(text: str) -> bool:
    return not text or bool(_SPEED_RE.match(text))


def is_valid_proxy(text: str) -> bool:
    return not text or bool(_PROXY_RE.match(text))


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


def _default_download_dir() -> str:
    return str(Path.home() / "Downloads")


@dataclass
class Settings:
    """Preferencias del usuario, persistidas en config.json."""

    download_path: str = field(default_factory=_default_download_dir)
    max_concurrent: int = 2
    quality: str = "Best"
    video_format: str = "mp4"
    audio_format: str = "mp3"
    audio_only: bool = False
    download_playlist: bool = False
    retries: int = 3
    enable_sounds: bool = True
    audio_langs: list[str] = field(default_factory=list)
    subs_mode: str = "none"
    subs_langs: list[str] = field(default_factory=lambda: ["es", "en"])
    subs_auto: bool = False
    embed_metadata: bool = False
    embed_thumbnail: bool = False
    speed_limit: str = ""
    proxy: str = ""
    cookies_browser: str = ""
    filename_template: str = FILENAME_TEMPLATES[0]
    monitor_clipboard: bool = False
    window_size: list[int] = field(default_factory=lambda: [960, 700])
    last_tab: int = 0
    cookies_file: str = ""
    use_archive: bool = False
    sponsorblock: str = "off"
    overwrite: str = "skip"
    notifications: bool = True
    allow_remote_components: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Sanea valores corruptos o editados a mano."""
        self.download_path = str(self.download_path).strip() or _default_download_dir()
        self.max_concurrent = _clamp(self.max_concurrent, 1, MAX_CONCURRENT_LIMIT, 2)
        self.retries = _clamp(self.retries, 0, MAX_RETRIES_LIMIT, 3)
        if not is_valid_quality(str(self.quality)):
            self.quality = "Best"
        if self.video_format not in VIDEO_FORMATS:
            self.video_format = "mp4"
        if self.audio_format not in AUDIO_FORMATS:
            self.audio_format = "mp3"
        if self.subs_mode not in SUBS_MODES:
            self.subs_mode = "none"
        if self.cookies_browser not in COOKIE_BROWSERS:
            self.cookies_browser = ""
        if self.filename_template not in FILENAME_TEMPLATES:
            self.filename_template = FILENAME_TEMPLATES[0]
        size = list(self.window_size) if isinstance(self.window_size, (list, tuple)) and len(self.window_size) == 2 else [960, 700]
        self.window_size = [_clamp(size[0], 640, 10000, 960), _clamp(size[1], 480, 10000, 700)]
        self.last_tab = _clamp(self.last_tab, 0, 3, 0)
        self.cookies_file = str(self.cookies_file).strip()
        if self.sponsorblock not in SPONSORBLOCK_MODES:
            self.sponsorblock = "off"
        if self.overwrite not in OVERWRITE_MODES:
            self.overwrite = "skip"
        self.profiles = _clean_profiles(self.profiles)
        self.audio_langs = lang_list(self.audio_langs)
        self.subs_langs = lang_list(self.subs_langs)
        self.speed_limit = str(self.speed_limit).strip()
        if not is_valid_speed(self.speed_limit):
            self.speed_limit = ""
        self.proxy = str(self.proxy).strip()
        if not is_valid_proxy(self.proxy):
            self.proxy = ""
        for name in (
            "audio_only", "download_playlist", "enable_sounds", "subs_auto",
            "embed_metadata", "embed_thumbnail", "monitor_clipboard",
            "use_archive", "notifications", "allow_remote_components",
        ):
            setattr(self, name, bool(getattr(self, name)))

    @classmethod
    def load(cls) -> Settings:
        """Carga config.json mezclando con los valores por defecto."""
        data = read_json(Paths.CONFIG_FILE, {})
        if not isinstance(data, dict):
            data = {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        """Guarda los ajustes en config.json (puede lanzar OSError)."""
        write_json(Paths.CONFIG_FILE, asdict(self))

    def download_options(self) -> dict[str, Any]:
        """Opciones que viajan con cada descarga (copia independiente)."""
        data = asdict(self)
        for key in ("max_concurrent", "enable_sounds", "monitor_clipboard", "window_size", "last_tab", "notifications", "profiles"):
            data.pop(key)
        return data


def sanitize_options(raw: Any) -> dict[str, Any]:
    """Valida opciones de descarga leídas de disco (cola restaurada) con las mismas reglas que Settings."""
    data = raw if isinstance(raw, dict) else {}
    known = {f.name for f in fields(Settings)}
    options = Settings(**{k: v for k, v in data.items() if k in known}).download_options()
    sections = [x for x in (data.get("sections") or []) if isinstance(x, str) and SECTION_RE.match(x)]
    if sections:
        options["sections"] = sections[:50]
    items = str(data.get("playlist_items") or "").replace(" ", "")
    if _ITEMS_RE.match(items):
        options["playlist_items"] = items
    return options


def sanitize_profile(raw: Any) -> dict[str, Any]:
    """Valida un perfil: solo claves permitidas y con las mismas reglas que Settings."""
    if not isinstance(raw, dict):
        return {}
    keys = PROFILE_KEYS & raw.keys()
    probe = Settings(**{k: raw[k] for k in keys})
    return {k: getattr(probe, k) for k in sorted(keys)}


def _clean_profiles(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for name, values in raw.items():
        title = str(name).strip()[:40]
        if title and isinstance(values, dict) and len(cleaned) < MAX_PROFILES:
            cleaned[title] = sanitize_profile(values)
    return cleaned
