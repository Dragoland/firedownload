"""Pestaña de ajustes: general, red, valores por defecto de subtítulos/metadatos y yt-dlp."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from firedownload.config import (
    COOKIE_BROWSERS,
    FILENAME_TEMPLATES,
    MAX_CONCURRENT_LIMIT,
    MAX_RETRIES_LIMIT,
    SUBS_MODES,
    Settings,
    is_valid_proxy,
    is_valid_speed,
    lang_list,
)
from firedownload.config import Paths
from firedownload.core.tasks import YtdlpTask
from firedownload.core.utils import find_js_runtime, open_in_file_manager
from firedownload.core.ytdlp import update_command, ytdlp_command
from firedownload.ui.check_dialog import CheckDialog
from firedownload.ui.log_dialog import LogDialog


class SettingsTab(QWidget):
    """Edita y guarda los ajustes generales."""

    settings_saved = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._task: YtdlpTask | None = None

        self._path = QLineEdit(settings.download_path)
        browse = QPushButton("Examinar…")
        self._concurrent = QSpinBox()
        self._concurrent.setRange(1, MAX_CONCURRENT_LIMIT)
        self._retries = QSpinBox()
        self._retries.setRange(0, MAX_RETRIES_LIMIT)
        self._template = QComboBox()
        self._template.addItems(FILENAME_TEMPLATES)
        self._sounds = QCheckBox("Sonido al completar o fallar una descarga")
        self._clipboard = QCheckBox("Rellenar la URL automáticamente al copiar un enlace")

        self._speed = QLineEdit()
        self._speed.setPlaceholderText("p. ej. 2M o 500K (vacío = sin límite)")
        self._proxy = QLineEdit()
        self._proxy.setPlaceholderText("p. ej. http://127.0.0.1:8080 o socks5://…")
        self._cookies = QComboBox()
        self._cookies.addItem("Ninguno", "")
        for browser in COOKIE_BROWSERS:
            self._cookies.addItem(browser.capitalize(), browser)

        self._audio_langs = QLineEdit()
        self._audio_langs.setPlaceholderText("p. ej. es,en (vacío = pista por defecto)")
        self._subs_mode = QComboBox()
        for key, label in SUBS_MODES.items():
            self._subs_mode.addItem(label, key)
        self._subs_langs = QLineEdit()
        self._subs_langs.setPlaceholderText("p. ej. es,en")
        self._subs_auto = QCheckBox("Permitir subtítulos generados automáticamente")
        self._embed_metadata = QCheckBox("Incrustar metadatos")
        self._embed_thumbnail = QCheckBox("Incrustar miniatura como carátula")

        self._version = QLabel("yt-dlp: …")
        self._version.setObjectName("muted")
        self._update = QPushButton("Actualizar yt-dlp")

        path_row = QHBoxLayout()
        path_row.addWidget(self._path, 1)
        path_row.addWidget(browse)

        general = QGroupBox("General")
        form = QFormLayout(general)
        form.addRow("Carpeta de descargas", path_row)
        form.addRow("Descargas simultáneas", self._concurrent)
        form.addRow("Reintentos", self._retries)
        form.addRow("Nombre de archivo", self._template)
        form.addRow("", self._sounds)
        form.addRow("", self._clipboard)

        network = QGroupBox("Red")
        net_form = QFormLayout(network)
        net_form.addRow("Límite de velocidad", self._speed)
        net_form.addRow("Proxy", self._proxy)
        net_form.addRow("Cookies del navegador", self._cookies)

        defaults = QGroupBox("Valores por defecto")
        def_form = QFormLayout(defaults)
        def_form.addRow("Pistas de audio preferidas", self._audio_langs)
        def_form.addRow("Subtítulos", self._subs_mode)
        def_form.addRow("Idiomas de subtítulos", self._subs_langs)
        def_form.addRow("", self._subs_auto)
        def_form.addRow("", self._embed_metadata)
        def_form.addRow("", self._embed_thumbnail)

        engine = QGroupBox("yt-dlp")
        engine_row = QHBoxLayout(engine)
        engine_row.addWidget(self._version, 1)
        engine_row.addWidget(self._update)

        runtime = find_js_runtime()
        js_label = QLabel(
            f"JavaScript: {runtime[0]} ({runtime[1]})" if runtime
            else "JavaScript: no encontrado. YouTube necesita Deno (o Node 20+) instalado."
        )
        js_label.setObjectName("muted" if runtime else "warning")
        js_label.setWordWrap(True)
        check_button = QPushButton("Comprobar instalación…")
        log_button = QPushButton("Ver registro…")
        data_button = QPushButton("Abrir carpeta de datos")
        diagnostics = QGroupBox("Diagnóstico")
        diag_layout = QVBoxLayout(diagnostics)
        diag_layout.addWidget(js_label)
        diag_buttons = QHBoxLayout()
        diag_buttons.addWidget(check_button)
        diag_buttons.addWidget(log_button)
        diag_buttons.addWidget(data_button)
        diag_buttons.addStretch(1)
        diag_layout.addLayout(diag_buttons)
        check_button.clicked.connect(lambda: CheckDialog(self._settings, self).exec())
        log_button.clicked.connect(lambda: LogDialog(self).exec())
        data_button.clicked.connect(lambda: open_in_file_manager(Paths.BASE))

        save = QPushButton("Guardar")
        save.setObjectName("primary")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 8)
        content_layout.setSpacing(14)
        for group in (general, network, defaults, engine, diagnostics):
            content_layout.addWidget(group)
        content_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 0, 24, 0)
        footer.addStretch(1)
        footer.addWidget(save, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(footer)

        browse.clicked.connect(self._browse)
        save.clicked.connect(self._save)
        self._update.clicked.connect(self._update_ytdlp)
        self._load_values()
        self._refresh_version()

    def _load_values(self) -> None:
        s = self._settings
        self._path.setText(s.download_path)
        self._concurrent.setValue(s.max_concurrent)
        self._retries.setValue(s.retries)
        self._template.setCurrentText(s.filename_template)
        self._sounds.setChecked(s.enable_sounds)
        self._clipboard.setChecked(s.monitor_clipboard)
        self._speed.setText(s.speed_limit)
        self._proxy.setText(s.proxy)
        self._cookies.setCurrentIndex(max(self._cookies.findData(s.cookies_browser), 0))
        self._audio_langs.setText(",".join(s.audio_langs))
        self._subs_mode.setCurrentIndex(max(self._subs_mode.findData(s.subs_mode), 0))
        self._subs_langs.setText(",".join(s.subs_langs))
        self._subs_auto.setChecked(s.subs_auto)
        self._embed_metadata.setChecked(s.embed_metadata)
        self._embed_thumbnail.setChecked(s.embed_thumbnail)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de descargas", self._path.text())
        if folder:
            self._path.setText(folder)

    def _save(self) -> None:
        raw = self._path.text().strip()
        if not raw:
            QMessageBox.warning(self, "Carpeta no válida", "Indica una carpeta de descargas.")
            return
        speed, proxy = self._speed.text().strip(), self._proxy.text().strip()
        if not is_valid_speed(speed):
            QMessageBox.warning(self, "Límite no válido", "Usa un número con sufijo K o M, por ejemplo 500K o 2M.")
            return
        if not is_valid_proxy(proxy):
            QMessageBox.warning(self, "Proxy no válido", "Formato esperado: http://host:puerto o socks5://host:puerto.")
            return
        folder = Path(raw).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Carpeta no válida", f"No se puede usar esa carpeta:\n{exc}")
            return

        s = self._settings
        s.download_path = str(folder)
        s.max_concurrent = self._concurrent.value()
        s.retries = self._retries.value()
        s.filename_template = self._template.currentText()
        s.enable_sounds = self._sounds.isChecked()
        s.monitor_clipboard = self._clipboard.isChecked()
        s.speed_limit = speed
        s.proxy = proxy
        s.cookies_browser = self._cookies.currentData()
        s.audio_langs = lang_list(self._audio_langs.text())
        s.subs_mode = self._subs_mode.currentData()
        s.subs_langs = lang_list(self._subs_langs.text())
        s.subs_auto = self._subs_auto.isChecked()
        s.embed_metadata = self._embed_metadata.isChecked()
        s.embed_thumbnail = self._embed_thumbnail.isChecked()
        try:
            s.save()
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar la configuración:\n{exc}")
            return
        self._load_values()
        self.settings_saved.emit()

    def _refresh_version(self) -> None:
        command = ytdlp_command(["--version"])
        if command is None:
            self._version.setText("yt-dlp: no encontrado")
            self._update.setEnabled(False)
            return
        task = YtdlpTask(command, 20)
        task.succeeded.connect(self._on_version)
        task.failed.connect(self._on_version_failed)
        task.start()

    def _on_version(self, output: str) -> None:
        self._version.setText(f"yt-dlp: {output.strip()}")

    def _on_version_failed(self, _message: str) -> None:
        self._version.setText("yt-dlp: versión desconocida")

    def _update_ytdlp(self) -> None:
        command = update_command()
        if command is None:
            return
        self._update.setEnabled(False)
        self._version.setText("Actualizando yt-dlp…")
        self._task = YtdlpTask(command, 300)
        self._task.succeeded.connect(self._on_updated)
        self._task.failed.connect(self._on_update_failed)
        self._task.start()

    def _on_updated(self, _output: str) -> None:
        self._update.setEnabled(True)
        self._refresh_version()

    def _on_update_failed(self, message: str) -> None:
        self._update.setEnabled(True)
        self._version.setText(f"No se pudo actualizar: {message}")
