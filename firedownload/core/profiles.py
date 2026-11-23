"""Perfiles de descarga: ajustes predefinidos y personalizados (sin Qt)."""

from __future__ import annotations

from typing import Any

from firedownload.config import PROFILE_KEYS, Settings, sanitize_profile

BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "Vídeo · mejor calidad (mp4)": {"quality": "Best", "video_format": "mp4", "audio_only": False},
    "Vídeo · 1080p (mp4)": {"quality": "1080p", "video_format": "mp4", "audio_only": False},
    "Vídeo · 720p ligero (mp4)": {"quality": "720p", "video_format": "mp4", "audio_only": False},
    "Música · MP3 con carátula": {
        "audio_only": True, "audio_format": "mp3", "embed_metadata": True, "embed_thumbnail": True,
    },
    "Música · M4A con carátula": {
        "audio_only": True, "audio_format": "m4a", "embed_metadata": True, "embed_thumbnail": True,
    },
    "Solo subtítulos (es, en)": {
        "subs_mode": "only", "subs_langs": ["es", "en"], "subs_auto": True, "audio_only": False,
    },
}


def all_profiles(settings: Settings) -> dict[str, dict[str, Any]]:
    """Perfiles predefinidos seguidos de los del usuario."""
    return {**BUILTIN_PROFILES, **{k: v for k, v in settings.profiles.items() if k not in BUILTIN_PROFILES}}


def snapshot(settings: Settings) -> dict[str, Any]:
    """Valores actuales de los ajustes que forman un perfil."""
    return sanitize_profile({key: getattr(settings, key) for key in PROFILE_KEYS})
