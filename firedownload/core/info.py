"""Metadatos y resultados de búsqueda de yt-dlp: argumentos y parseo de JSON (sin Qt)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from firedownload.core.ytdlp import common_args

_YT_ID_RE = re.compile(r"^[\w-]{11}$")


@dataclass
class MediaInfo:
    """Metadatos de un vídeo o playlist."""

    url: str
    title: str = ""
    uploader: str = ""
    duration: float | None = None
    upload_date: str = ""
    view_count: int | None = None
    thumbnail: str = ""
    description: str = ""
    is_playlist: bool = False
    playlist_count: int = 0
    playlist_entries: list[tuple[int, str]] = field(default_factory=list)
    heights: list[int] = field(default_factory=list)
    audio_tracks: list[tuple[str, str]] = field(default_factory=list)
    subtitles: list[tuple[str, str]] = field(default_factory=list)
    auto_captions: list[tuple[str, str]] = field(default_factory=list)
    chapters: int = 0
    chapter_list: list[tuple[float, float, str]] = field(default_factory=list)


@dataclass
class SearchResult:
    """Un resultado de búsqueda."""

    title: str
    url: str
    channel: str = ""
    duration: float | None = None
    thumbnail: str = ""


def info_args(url: str, options: Mapping[str, Any], *, playlist: bool = False) -> list[str]:
    return [
        "-J", "--no-warnings",
        "--flat-playlist" if playlist else "--no-playlist",
        *common_args(options), "--", url,
    ]


def stream_args(url: str, options: Mapping[str, Any]) -> list[str]:
    """Pide la URL directa de un stream único (vídeo+audio) de calidad moderada."""
    selector = "best[vcodec!=none][acodec!=none][height<=480]/best[vcodec!=none][acodec!=none]"
    return ["-g", "-f", selector, "--no-playlist", "--no-warnings", *common_args(options), "--", url]


def search_args(prefix: str, query: str, limit: int, options: Mapping[str, Any]) -> list[str]:
    term = " ".join(query.split())
    return ["-J", "--flat-playlist", "--no-warnings", *common_args(options), f"{prefix}{limit}:{term}"]


def compress_ranges(indices: list[int]) -> str:
    """[1, 2, 3, 5, 7, 8] → «1-3,5,7-8» (formato de --playlist-items)."""
    numbers = sorted(set(indices))
    parts: list[str] = []
    start = prev = None
    for n in numbers:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            parts.append(f"{start}-{prev}" if prev > start else str(start))
            start = prev = n
    if start is not None:
        parts.append(f"{start}-{prev}" if prev > start else str(start))
    return ",".join(parts)


def _best_thumbnail(data: Mapping[str, Any], target_width: int = 320) -> str:
    """Miniatura más cercana al ancho objetivo (o la declarada en 'thumbnail')."""
    thumbs = [t for t in data.get("thumbnails") or [] if isinstance(t, dict) and t.get("url")]
    if thumbs:
        sized = [t for t in thumbs if isinstance(t.get("width"), int)]
        if sized:
            enough = [t for t in sized if t["width"] >= target_width]
            pick = min(enough, key=lambda t: t["width"]) if enough else max(sized, key=lambda t: t["width"])
            return str(pick["url"])
    if data.get("thumbnail"):
        return str(data["thumbnail"])
    if thumbs:
        return str(thumbs[-1]["url"])
    vid = str(data.get("id") or "")
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if _YT_ID_RE.match(vid) and "youtube" in str(data.get("ie_key", "")).lower() else ""


def _caption_list(raw: Any) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if not isinstance(raw, dict):
        return result
    for code, entries in raw.items():
        if code == "live_chat":
            continue
        name = ""
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            name = str(entries[0].get("name") or "")
        result.append((str(code), name))
    return result


def parse_info(raw: str, url: str) -> MediaInfo:
    """Convierte la salida de `yt-dlp -J` en MediaInfo (ValueError si no es JSON válido)."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Respuesta inesperada de yt-dlp")
    info = MediaInfo(
        url=url,
        title=str(data.get("title") or url),
        uploader=str(data.get("uploader") or data.get("channel") or ""),
        duration=data.get("duration"),
        upload_date=str(data.get("upload_date") or ""),
        view_count=data.get("view_count"),
        description=str(data.get("description") or ""),
        thumbnail=_best_thumbnail(data, 640),
    )
    if data.get("_type") == "playlist":
        raw_entries = data.get("entries") or []
        entries = [e for e in raw_entries if isinstance(e, dict)]
        info.is_playlist = True
        info.playlist_count = len(entries)
        info.playlist_entries = [
            (position, str(e.get("title") or e.get("id") or f"#{position}"))
            for position, e in enumerate(raw_entries, start=1)
            if isinstance(e, dict)
        ]
        if not info.thumbnail and entries:
            info.thumbnail = _best_thumbnail(entries[0], 640)
        return info

    heights: set[int] = set()
    tracks: dict[str, str] = {}
    for fmt in data.get("formats") or []:
        if not isinstance(fmt, dict):
            continue
        if fmt.get("vcodec") not in (None, "none") and isinstance(fmt.get("height"), int):
            heights.add(fmt["height"])
        language = fmt.get("language")
        if language and fmt.get("acodec") not in (None, "none") and language not in tracks:
            tracks[str(language)] = str(fmt.get("format_note") or "")
    info.heights = sorted(heights, reverse=True)
    info.audio_tracks = sorted(tracks.items())
    info.subtitles = _caption_list(data.get("subtitles"))
    info.auto_captions = _caption_list(data.get("automatic_captions"))
    for chapter in data.get("chapters") or []:
        if isinstance(chapter, dict) and isinstance(chapter.get("start_time"), (int, float)) and isinstance(chapter.get("end_time"), (int, float)):
            info.chapter_list.append((float(chapter["start_time"]), float(chapter["end_time"]), str(chapter.get("title") or "")))
    info.chapters = len(data.get("chapters") or [])
    return info


def parse_search(raw: str) -> list[SearchResult]:
    """Convierte la salida de una búsqueda `--flat-playlist -J` en resultados."""
    data = json.loads(raw)
    results: list[SearchResult] = []
    for entry in (data.get("entries") or []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or entry.get("webpage_url") or "")
        ident = str(entry.get("id") or "")
        if not url.startswith("http"):
            if _YT_ID_RE.match(url or ident):
                url = f"https://www.youtube.com/watch?v={url or ident}"
            else:
                continue
        results.append(
            SearchResult(
                title=str(entry.get("title") or url),
                url=url,
                channel=str(entry.get("channel") or entry.get("uploader") or ""),
                duration=entry.get("duration"),
                thumbnail=_best_thumbnail(entry),
            )
        )
    return results
