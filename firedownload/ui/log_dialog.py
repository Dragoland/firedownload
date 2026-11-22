"""Visor del registro de la aplicación (logs/app.log)."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from firedownload.config import Paths
from firedownload.core.utils import open_in_file_manager, read_tail


class LogDialog(QDialog):
    """Muestra las últimas líneas del registro para diagnosticar problemas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Registro de FireDownload")
        self.resize(860, 520)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        refresh = QPushButton("Actualizar")
        copy = QPushButton("Copiar todo")
        folder = QPushButton("Abrir carpeta")
        close = QPushButton("Cerrar")
        refresh.clicked.connect(self._load)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._text.toPlainText()))
        folder.clicked.connect(lambda: open_in_file_manager(Paths.LOGS))
        close.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        for button in (refresh, copy, folder):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self._text, 1)
        layout.addLayout(buttons)
        self._load()

    def _load(self) -> None:
        self._text.setPlainText(read_tail(Paths.LOG_FILE, 400) or "El registro está vacío.")
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())
