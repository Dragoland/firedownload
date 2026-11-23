"""Ventana principal: cabecera con logo, menú, pestañas y barra de estado."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from firedownload import __version__
from firedownload.config import Settings
from firedownload.core import notify
from firedownload.core.manager import DownloadManager, Status
from firedownload.core.tasks import YtdlpTask
from firedownload.core.thumbs import ThumbnailLoader
from firedownload.core.utils import (
    check_ffmpeg,
    find_js_runtime,
    find_logo,
    find_ytdlp,
    format_speed,
    is_playlist_url,
    ytdlp_is_outdated,
)
from firedownload.core.ytdlp import ytdlp_command
from firedownload.ui.about_dialog import AboutDialog
from firedownload.ui.check_dialog import CheckDialog
from firedownload.ui.download_tab import DownloadTab
from firedownload.ui.history_tab import HistoryTab
from firedownload.ui.info_dialog import InfoDialog
from firedownload.ui.log_dialog import LogDialog
from firedownload.ui.search_tab import SearchTab
from firedownload.ui.settings_tab import SettingsTab
from firedownload.ui.tools_dialog import ToolsDialog


class MainWindow(QMainWindow):
    """Contenedor de las pestañas Descargas, Buscar, Historial y Ajustes."""

    def __init__(self, settings: Settings, manager: DownloadManager, loader: ThumbnailLoader) -> None:
        super().__init__()
        self._settings = settings
        self._manager = manager
        self._loader = loader
        self.setWindowTitle(f"FireDownload {__version__}")
        self.setMinimumSize(800, 580)
        self.resize(*settings.window_size)

        self._download_tab = DownloadTab(settings, manager, loader)
        self._search_tab = SearchTab(settings, loader)
        self._history_tab = HistoryTab()
        self._settings_tab = SettingsTab(settings)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._download_tab, "Descargas")
        self._tabs.addTab(self._search_tab, "Buscar")
        self._tabs.addTab(self._history_tab, "Historial")
        self._tabs.addTab(self._settings_tab, "Ajustes")
        self._tabs.setCurrentIndex(min(settings.last_tab, self._tabs.count() - 1))

        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self._tabs, 1)
        self.setCentralWidget(central)
        self._build_menus()

        self._speed = QLabel()
        self._warnings = QLabel()
        self._warnings.setObjectName("warning")
        self._ytdlp_outdated = ""
        self.statusBar().addPermanentWidget(self._warnings)
        self.statusBar().addPermanentWidget(self._speed)
        self._speed_timer = QTimer(self)
        self._speed_timer.timeout.connect(self._update_speed)
        self._speed_timer.start(1000)

        manager.download_finished.connect(self._on_download_finished)
        self._download_tab.analyze_requested.connect(self.show_details)
        self._download_tab.status_message.connect(lambda text: self.statusBar().showMessage(text, 5000))
        self._search_tab.details_requested.connect(self.show_details)
        self._search_tab.download_requested.connect(self._download_from_search)
        self._history_tab.redownload_requested.connect(self._redownload)
        self._settings_tab.settings_saved.connect(self._on_settings_saved)
        self._download_tab.tools_requested.connect(self.show_tools)
        self._settings_tab.tools_requested.connect(self.show_tools)
        self._refresh_warnings()
        QTimer.singleShot(0, self._startup_checks)
        restored = manager.restore()
        if restored:
            self.statusBar().showMessage(
                f"{restored} descargas pendientes de la sesión anterior: pulsa «Reanudar pendientes»", 10000
            )

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 10, 18, 10)
        row.setSpacing(12)
        logo_path = find_logo()
        if logo_path is not None:
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo = QLabel()
                logo.setPixmap(pixmap.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation))
                row.addWidget(logo)
        brand = QLabel("FireDownload")
        brand.setObjectName("brand")
        version = QLabel(f"v{__version__}")
        version.setObjectName("muted")
        about = QPushButton("Acerca de")
        about.setObjectName("link")
        about.setCursor(Qt.CursorShape.PointingHandCursor)
        about.clicked.connect(self.show_about)
        row.addWidget(brand)
        row.addWidget(version)
        row.addStretch(1)
        row.addWidget(about)
        return header

    def _add_action(self, menu: QMenu, text: str, slot: Callable[[], object], shortcut: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Archivo")
        self._add_action(file_menu, "Importar lista de URLs…", self._download_tab.import_list, "Ctrl+O")
        file_menu.addSeparator()
        self._add_action(file_menu, "Salir", self.close, "Ctrl+Q")

        downloads = bar.addMenu("&Descargas")
        self._add_action(downloads, "Pegar URL del portapapeles y añadir", self._download_tab.paste_and_add, "Ctrl+Shift+V")
        downloads.addSeparator()
        self._add_action(downloads, "Pausar todo", self._manager.pause_all, "Ctrl+P")
        self._add_action(downloads, "Reanudar todo", self._resume_everything, "Ctrl+R")
        self._add_action(downloads, "Quitar terminadas", self._manager.clear_finished, "Ctrl+L")

        view = bar.addMenu("&Ver")
        for index, (title, widget) in enumerate(
            (
                ("Descargas", self._download_tab),
                ("Buscar", self._search_tab),
                ("Historial", self._history_tab),
                ("Ajustes", self._settings_tab),
            ),
            start=1,
        ):
            self._add_action(view, title, lambda w=widget: self._tabs.setCurrentWidget(w), f"Ctrl+{index}")
        self._add_action(view, "Buscar vídeos…", self._focus_search, "Ctrl+F")

        help_menu = bar.addMenu("A&yuda")
        self._add_action(help_menu, "Herramientas (yt-dlp, FFmpeg, Deno)…", self.show_tools)
        self._add_action(help_menu, "Comprobar instalación…", lambda: CheckDialog(self._settings, self).exec())
        self._add_action(help_menu, "Ver registro…", lambda: LogDialog(self).exec())
        help_menu.addSeparator()
        self._add_action(help_menu, "Acerca de FireDownload", self.show_about, "F1")

    def _resume_everything(self) -> None:
        self._manager.resume_all()
        self._manager.resume_pending()

    def _focus_search(self) -> None:
        self._tabs.setCurrentWidget(self._search_tab)
        self._search_tab.focus_query()

    def show_about(self) -> None:
        AboutDialog(self._settings, self).exec()

    def _update_speed(self) -> None:
        active = len(self._manager.active)
        if active:
            self._speed.setText(f"↓ {format_speed(self._manager.total_speed())} · {active} activas")
        else:
            self._speed.setText("")

    def _refresh_warnings(self) -> None:
        warnings = []
        if find_ytdlp() is None:
            warnings.append("yt-dlp no encontrado")
        elif self._ytdlp_outdated:
            warnings.append(f"yt-dlp desactualizado ({self._ytdlp_outdated})")
        if find_js_runtime() is None:
            warnings.append("Sin Deno/Node: YouTube puede fallar")
        if not check_ffmpeg():
            warnings.append("Sin FFmpeg: calidad limitada, sin conversión de audio")
        self._warnings.setText(" · ".join(warnings))
        self._download_tab.refresh_banner()

    def _startup_checks(self) -> None:
        """Ofrece instalar lo que falte y avisa si yt-dlp está desactualizado."""
        if find_ytdlp() is None:
            self.show_tools()
            return
        command = ytdlp_command(["--version"])
        if command is not None:
            self._version_task = YtdlpTask(command, 20)
            self._version_task.succeeded.connect(self._on_ytdlp_version)
            self._version_task.start()

    def _on_ytdlp_version(self, output: str) -> None:
        version = output.strip()
        self._ytdlp_outdated = version if ytdlp_is_outdated(version) else ""
        self._refresh_warnings()

    def show_tools(self) -> None:
        dialog = ToolsDialog(self)
        dialog.tools_changed.connect(self._on_tools_changed)
        dialog.exec()
        self._on_tools_changed()

    def _on_tools_changed(self) -> None:
        self._ytdlp_outdated = ""
        self._refresh_warnings()
        self._settings_tab.refresh_version()
        self._startup_version_check()

    def _startup_version_check(self) -> None:
        if find_ytdlp() is not None:
            self._startup_checks()

    def handle_external(self, message: str) -> None:
        """Mensaje de otra instancia: trae la ventana al frente y añade las URLs recibidas."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        urls = [line.strip() for line in message.splitlines() if line.strip().startswith("http")]
        if urls:
            self._tabs.setCurrentWidget(self._download_tab)
            self._download_tab.add_urls(urls)

    def show_details(self, url: str, playlist: bool = False) -> None:
        """Abre el visor de metadatos y encola la descarga si el usuario acepta."""
        dialog = InfoDialog(url, self._settings, self._loader, playlist=playlist or is_playlist_url(url), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.info is not None:
            info = dialog.info
            self._manager.add(url, dialog.options(), title="" if info.is_playlist else info.title, thumbnail=info.thumbnail)
            self._tabs.setCurrentWidget(self._download_tab)

    def _download_from_search(self, url: str, title: str, thumbnail: str) -> None:
        self._download_tab.add_urls([url], title=title, thumbnail=thumbnail)
        self.statusBar().showMessage(f"Añadido: {title}", 4000)

    def _on_download_finished(self, item_id: str, ok: bool) -> None:
        item = self._manager.items.get(item_id)
        if ok:
            self._history_tab.reload()
        if item is not None and item.status is not Status.CANCELLED:
            verdict = "Completado" if ok else "Falló"
            self.statusBar().showMessage(f"{verdict}: {item.display_title}", 6000)
            if self._settings.notifications and not self.isActiveWindow():
                notify.send(f"FireDownload · {verdict}", item.display_title)

    def _on_settings_saved(self) -> None:
        self._manager.apply_settings()
        self.statusBar().showMessage("Ajustes guardados", 3000)

    def _redownload(self, url: str) -> None:
        self._download_tab.add_urls([url])
        self._tabs.setCurrentWidget(self._download_tab)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._manager.busy:
            answer = QMessageBox.question(
                self,
                "Descargas en curso",
                "Hay descargas activas o en cola. ¿Salir y cancelarlas?",
                defaultButton=QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._remember_layout()
        event.accept()

    def _remember_layout(self) -> None:
        """Guarda tamaño de ventana y pestaña activa para la próxima sesión."""
        if not self.isMaximized() and not self.isFullScreen():
            self._settings.window_size = [self.width(), self.height()]
        self._settings.last_tab = self._tabs.currentIndex()
        try:
            self._settings.save()
        except OSError:
            pass
