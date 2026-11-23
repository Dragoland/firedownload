"""Construcción de comandos de yt-dlp y traducción de errores (sin Qt)."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from firedownload.config import _ITEMS_RE, FILENAME_TEMPLATES, SECTION_RE, Paths, quality_height
from firedownload.core.utils import find_js_runtime, find_tool, find_ytdlp

_THUMBNAIL_EXTS = frozenset({"mp3", "m4a", "opus", "flac", "mp4", "mkv"})

_ERROR_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("sign in to confirm",), "YouTube pide verificación (bloqueo anti-bots). Actualiza yt-dlp o usa las cookies del navegador en Ajustes."),
    (("private video",), "El vídeo es privado."),
    (("video unavailable", "this video is not available"), "El vídeo no está disponible."),
    (("unsupported url",), "URL no soportada por yt-dlp."),
    (("http error 429",), "Demasiadas peticiones (429). Espera unos minutos."),
    (("http error 403",), "Acceso denegado (403). Actualiza yt-dlp o prueba más tarde."),
    (("requested format is not available",), "El formato pedido no está disponible para este vídeo."),
    (("ffmpeg", "ffprobe"), "FFmpeg no está instalado o no se encuentra en el PATH."),
    (
        ("getaddrinfo", "name resolution", "network is unreachable", "timed out", "unable to download webpage"),
        "Sin conexión o red inestable.",
    ),
)


def humanize_error(text: str) -> str:
    """Traduce errores típicos de yt-dlp a mensajes legibles."""
    lowered = text.lower()
    for keys, message in _ERROR_HINTS:
        if any(key in lowered for key in keys):
            return message
    return text.removeprefix("ERROR:").strip() or "Error desconocido."


def ytdlp_command(args: Sequence[str]) -> list[str] | None:
    """Comando completo (ejecutable + argumentos) o None si yt-dlp no está disponible."""
    base = find_ytdlp()
    return [*base, *args] if base else None


def ffmpeg_location_args() -> list[str]:
    """Si FFmpeg lo instaló la app, le dice a yt-dlp dónde está."""
    managed = find_tool("ffmpeg")
    return ["--ffmpeg-location", str(managed.parent)] if managed else []


def js_runtime_args(*, allow_remote: bool = False) -> list[str]:
    """Indica a yt-dlp qué runtime de JavaScript usar (necesario para YouTube)."""
    runtime = find_js_runtime()
    if runtime is None:
        return []
    name, path = runtime
    args = ["--js-runtimes", f"{name}:{path}"]
    base = find_ytdlp()
    if allow_remote and base and base[1:3] == ("-m", "yt_dlp") and importlib.util.find_spec("yt_dlp_ejs") is None:
        args += ["--remote-components", "ejs:github"]
    return args


def common_args(options: Mapping[str, Any], *, js: bool = True) -> list[str]:
    """Argumentos de entorno compartidos por descargas, metadatos y búsquedas."""
    args: list[str] = js_runtime_args(allow_remote=bool(options.get("allow_remote_components"))) if js else []
    args += ffmpeg_location_args()
    if options.get("proxy"):
        args += ["--proxy", str(options["proxy"])]
    cookies_file = str(options.get("cookies_file") or "")
    if cookies_file and Path(cookies_file).is_file():
        args += ["--cookies", cookies_file]
    elif options.get("cookies_browser"):
        args += ["--cookies-from-browser", str(options["cookies_browser"])]
    return args


def format_selector(height: int | None, langs: Sequence[str]) -> str:
    """Selector de formato de yt-dlp con tope de altura y pistas de audio preferidas."""
    cap = f"[height<={height}]" if height else ""
    plain = f"bv*{cap}+ba/b{cap}"
    if not langs:
        return plain
    tracks = "".join(f"+ba[language^={lang}]" for lang in langs)
    return f"bv*{cap}{tracks}/bv*{cap}+ba[language^={langs[0]}]/{plain}"


def build_args(
    url: str,
    options: Mapping[str, Any],
    *,
    ffmpeg: bool = True,
    js: bool = True,
    fallback: bool = False,
) -> list[str]:
    """Argumentos de yt-dlp para una descarga. `fallback` usa un selector de formato sin restricciones."""
    retries = str(options["retries"])
    audio_only = bool(options["audio_only"])
    langs = list(options.get("audio_langs") or [])
    sub_langs = list(options.get("subs_langs") or [])
    sub_mode = str(options.get("subs_mode", "none")) if sub_langs else "none"
    template = str(Path(str(options["download_path"])) / str(options.get("filename_template") or FILENAME_TEMPLATES[0]))

    args = [
        "--newline",
        "--retries", retries,
        "--fragment-retries", retries,
        "--socket-timeout", "30",
        "--concurrent-fragments", "4",
        "--trim-filenames", "180",
        "--yes-playlist" if options["download_playlist"] else "--no-playlist",
        "-o", template,
        *common_args(options, js=js),
    ]
    items = str(options.get("playlist_items") or "").replace(" ", "")
    if options["download_playlist"] and _ITEMS_RE.match(items):
        args += ["--playlist-items", items]
    if options.get("speed_limit"):
        args += ["--limit-rate", str(options["speed_limit"])]
    if options.get("use_archive"):
        args += ["--download-archive", str(Paths.ARCHIVE_FILE)]
    if options.get("overwrite") == "overwrite":
        args.append("--force-overwrites")

    if sub_mode == "embed" and (audio_only or not ffmpeg):
        sub_mode = "files"
    if sub_mode != "none":
        args += ["--write-subs", "--sub-langs", ",".join(sub_langs)]
        if options.get("subs_auto"):
            args.append("--write-auto-subs")
        if sub_mode == "embed":
            args.append("--embed-subs")
        elif ffmpeg:
            args += ["--convert-subs", "srt"]
    if sub_mode == "only":
        return [*args, "--skip-download", "--", url]

    cap = quality_height(str(options["quality"]))
    if audio_only and ffmpeg:
        container = str(options["audio_format"])
        selector = f"ba[language^={langs[0]}]/ba/b" if langs else "ba/b"
        args += ["-f", selector, "-x", "--audio-format", container, "--audio-quality", "0"]
    elif audio_only:
        container = "m4a"
        args += ["-f", "ba[ext=m4a]/ba/b"]
    elif fallback:
        container = str(options["video_format"])
        args += ["-f", "bv*+ba/b" if ffmpeg else "b"]
        if ffmpeg:
            args += ["--merge-output-format", container]
    elif ffmpeg:
        multi = len(langs) > 1
        container = "mkv" if multi else str(options["video_format"])
        args += ["-f", format_selector(cap, langs), "--merge-output-format", container]
        if container == "mp4":
            args += ["-S", "res,vcodec:h264,acodec:m4a"]
        if multi:
            args.append("--audio-multistreams")
    else:
        container = "mp4"
        limit = f"[height<={cap}]" if cap else ""
        args += ["-f", f"b{limit}/b"]

    sections = [x for x in (options.get("sections") or []) if SECTION_RE.match(str(x))]
    if ffmpeg and sections:
        for section in sections:
            args += ["--download-sections", str(section)]
        args.append("--force-keyframes-at-cuts")
    sponsorblock = options.get("sponsorblock", "off")
    if ffmpeg and sponsorblock == "remove":
        args += ["--sponsorblock-remove", "sponsor,selfpromo,interaction"]
    elif ffmpeg and sponsorblock == "mark":
        args += ["--sponsorblock-mark", "all"]
    if ffmpeg and options.get("embed_metadata"):
        args.append("--embed-metadata")
    if ffmpeg and options.get("embed_thumbnail") and container in _THUMBNAIL_EXTS:
        args.append("--embed-thumbnail")
    return [*args, "--", url]
