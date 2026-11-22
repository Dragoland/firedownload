"""Pestaña de historial con filtro y menú contextual."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from firedownload.core import history
from firedownload.core.utils import open_file, open_in_file_manager


class HistoryTab(QWidget):
    """Lista de descargas completadas."""

    redownload_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrar por título, sitio o URL…")
        self._filter.setClearButtonEnabled(True)
        self._clear = QPushButton("Limpiar historial")
        self._clear.setObjectName("danger")
        self._count = QLabel()
        self._count.setObjectName("muted")
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        top = QHBoxLayout()
        top.addWidget(self._filter, 1)
        top.addWidget(self._clear)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._count)

        self._filter.textChanged.connect(self._apply_filter)
        self._clear.clicked.connect(self._on_clear)
        self._list.customContextMenuRequested.connect(self._show_menu)
        self._list.itemDoubleClicked.connect(lambda item: self._play(item.data(Qt.ItemDataRole.UserRole)))
        self.reload()

    def reload(self) -> None:
        """Relee history.json (más recientes primero)."""
        self._list.clear()
        for entry in reversed(history.load()):
            title = entry.get("title") or entry.get("url", "")
            date = str(entry.get("date", "")).replace("T", " ")
            details = " · ".join(str(p) for p in (entry.get("site"), entry.get("format"), date) if p)
            item = QListWidgetItem(f"{title}\n{details}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._list.addItem(item)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self._filter.text().strip().casefold()
        visible = 0
        for i in range(self._list.count()):
            item = self._list.item(i)
            entry = item.data(Qt.ItemDataRole.UserRole)
            haystack = " ".join(str(entry.get(k, "")) for k in ("title", "url", "site")).casefold()
            hidden = needle not in haystack
            item.setHidden(hidden)
            visible += not hidden
        self._count.setText(f"{visible} de {self._list.count()} descargas")
        self._clear.setEnabled(self._list.count() > 0)

    def _show_menu(self, pos: Any) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Reproducir").triggered.connect(lambda: self._play(entry))
        menu.addAction("Abrir carpeta").triggered.connect(lambda: self._open_folder(entry))
        menu.addAction("Copiar URL").triggered.connect(lambda: QGuiApplication.clipboard().setText(entry.get("url", "")))
        menu.addAction("Descargar de nuevo").triggered.connect(
            lambda: self.redownload_requested.emit(entry.get("url", ""))
        )
        menu.addSeparator()
        menu.addAction("Eliminar del historial").triggered.connect(lambda: self._delete(entry))
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _open_folder(self, entry: dict[str, Any]) -> None:
        raw = entry.get("path")
        if not raw or not open_in_file_manager(Path(raw)):
            QMessageBox.warning(self, "No se pudo abrir", "La carpeta o el archivo ya no existe.")

    def _play(self, entry: dict[str, Any]) -> None:
        raw = entry.get("path")
        if not raw or not open_file(Path(raw)):
            QMessageBox.warning(self, "No se pudo abrir", "El archivo ya no existe o no tiene reproductor asociado.")

    def _delete(self, entry: dict[str, Any]) -> None:
        try:
            history.remove_by_url(entry.get("url", ""))
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo actualizar el historial:\n{exc}")
        self.reload()

    def _on_clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Limpiar historial",
            "¿Eliminar todo el historial? Los archivos descargados no se borran.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            history.clear()
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo limpiar el historial:\n{exc}")
        self.reload()
