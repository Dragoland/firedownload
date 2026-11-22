"""Persistencia de la cola de descargas pendientes (queue.json)."""

from __future__ import annotations

from typing import Any

from firedownload.config import Paths
from firedownload.core.utils import read_json, write_json


def load() -> list[dict[str, Any]]:
    """Entradas guardadas: {url, options, title, thumbnail}."""
    data = read_json(Paths.QUEUE_FILE, [])
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("url"), str)]


def save(entries: list[dict[str, Any]]) -> None:
    """Sobrescribe la cola guardada (puede lanzar OSError)."""
    write_json(Paths.QUEUE_FILE, entries)
