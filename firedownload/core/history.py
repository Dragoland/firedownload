"""Historial de descargas completadas (history.json)."""

from __future__ import annotations

from typing import Any

from firedownload.config import Paths
from firedownload.core.utils import read_json, write_json


def load() -> list[dict[str, Any]]:
    """Entradas del historial, de la más antigua a la más reciente."""
    data = read_json(Paths.HISTORY_FILE, [])
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _save(entries: list[dict[str, Any]]) -> None:
    write_json(Paths.HISTORY_FILE, entries)


def add(entry: dict[str, Any]) -> None:
    """Añade una entrada al final."""
    entries = load()
    entries.append(entry)
    _save(entries)


def remove_by_url(url: str) -> None:
    """Elimina todas las entradas con esa URL."""
    _save([entry for entry in load() if entry.get("url") != url])


def clear() -> None:
    """Vacía el historial."""
    _save([])
