"""Pruebas de interfaz con Qt en modo offscreen (requieren PySide6 completo)."""

import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("psutil")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from firedownload.core import queue_store  # noqa: E402
from firedownload.core.manager import DownloadManager, Status  # noqa: E402
from firedownload.core.thumbs import ThumbnailLoader  # noqa: E402
from firedownload.ui.download_tab import DownloadTab  # noqa: E402
from firedownload.ui.about_dialog import AboutDialog  # noqa: E402
from firedownload.ui.check_dialog import CheckDialog  # noqa: E402
from firedownload.ui.info_dialog import InfoDialog  # noqa: E402
from firedownload.ui.main_window import MainWindow  # noqa: E402
from firedownload.ui.search_tab import SearchTab  # noqa: E402

VIDEO = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
PLAYLIST = "https://www.youtube.com/playlist?list=PL123"


@pytest.fixture
def app_parts(fake_ytdlp, settings, qapp, monkeypatch):
    monkeypatch.setattr("firedownload.ui.download_tab.free_space", lambda _path: 10**12)
    loader = ThumbnailLoader(qapp)
    manager = DownloadManager(settings)
    yield settings, manager, loader
    manager.shutdown()


def test_window_builds(app_parts):
    settings, manager, loader = app_parts
    window = MainWindow(settings, manager, loader)
    assert window.windowTitle().startswith("FireDownload")
    assert window._tabs.count() == 4


def test_add_url_creates_card_and_completes(app_parts, wait):
    settings, manager, loader = app_parts
    tab = DownloadTab(settings, manager, loader)
    tab._url.setText(VIDEO)
    tab._add.click()
    assert len(manager.items) == 1 and len(tab._cards) == 1
    item = next(iter(manager.items.values()))
    assert wait(lambda: item.status is Status.COMPLETED)
    assert tab._cards[item.id]._state.text() == "Completado"
    assert tab._url.text() == ""


def test_invalid_url_is_rejected(app_parts, monkeypatch):
    settings, manager, loader = app_parts
    shown = []
    monkeypatch.setattr("firedownload.ui.download_tab.QMessageBox.warning", lambda *a, **k: shown.append(a))
    tab = DownloadTab(settings, manager, loader)
    tab._url.setText("esto no es una url")
    tab._add.click()
    assert shown and not manager.items


@pytest.mark.parametrize("choice, expected_items", [("cancel", 0), ("all", 1)])
def test_playlist_url_asks_before_downloading_everything(app_parts, monkeypatch, choice, expected_items):
    settings, manager, loader = app_parts
    tab = DownloadTab(settings, manager, loader)
    monkeypatch.setattr(tab, "_ask_playlist", lambda single: choice)
    tab._url.setText(PLAYLIST)
    tab._add.click()
    assert len(manager.items) == expected_items
    if expected_items:
        assert next(iter(manager.items.values())).options["download_playlist"] is True


def test_pending_items_show_resume_button(app_parts):
    settings, manager, loader = app_parts
    queue_store.save([{"url": VIDEO, "options": {}, "title": "Anterior"}])
    tab = DownloadTab(settings, manager, loader)
    assert manager.restore() == 1
    item = next(iter(manager.items.values()))
    assert item.status is Status.PENDING
    assert "Pendiente" in tab._cards[item.id]._state.text()
    assert not tab._resume_pending.isHidden()


def test_info_dialog_for_a_video(app_parts, wait):
    settings, _manager, loader = app_parts
    dialog = InfoDialog(VIDEO, settings, loader)
    assert wait(lambda: dialog.info is not None)
    assert dialog.info.title == "Vídeo falso"
    assert [dialog._quality.itemText(i) for i in range(dialog._quality.count())] == ["Best", "1080p", "720p"]
    options = dialog.options()
    assert options["quality"] == "Best" and options["audio_langs"] == []
    dialog.reject()


def test_info_dialog_selects_audio_tracks_and_subtitles(app_parts, wait):
    settings, _manager, loader = app_parts
    dialog = InfoDialog(VIDEO, settings, loader)
    assert wait(lambda: dialog.info is not None)
    for i in range(dialog._audio_list.count()):
        dialog._audio_list.item(i).setCheckState(Qt.CheckState.Checked)
    dialog._subs_list.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._subs_mode.setCurrentIndex(dialog._subs_mode.findData("files"))
    options = dialog.options()
    assert options["audio_langs"] == ["en-US", "es-US"]
    assert options["subs_mode"] == "files" and options["subs_langs"] == ["es"] and options["subs_auto"] is False
    dialog.reject()


def test_info_dialog_playlist_item_selection(app_parts, wait):
    settings, _manager, loader = app_parts
    dialog = InfoDialog(PLAYLIST, settings, loader, playlist=True)
    assert wait(lambda: dialog.info is not None)
    assert dialog.info.is_playlist and dialog._items_list.count() == 3
    dialog._items_list.item(1).setCheckState(Qt.CheckState.Unchecked)
    options = dialog.options()
    assert options["playlist_items"] == "1,3" and options["download_playlist"] is True
    dialog.reject()


def test_search_tab_lists_results(app_parts, wait):
    settings, _manager, loader = app_parts
    tab = SearchTab(settings, loader)
    tab._query.setText("algo")
    tab._go.click()
    assert wait(lambda: tab._list.count() == 2)
    tab._list.setCurrentRow(0)
    requested = []
    tab.download_requested.connect(lambda *args: requested.append(args))
    tab._download.click()
    assert requested[0][0].endswith("aaaaaaaaaaa") and requested[0][1] == "Resultado uno"


def test_search_ignores_results_of_a_replaced_search(app_parts, wait):
    settings, _manager, loader = app_parts
    tab = SearchTab(settings, loader)
    tab._query.setText("uno")
    tab._go.click()
    tab._query.setText("dos")
    tab._go.click()
    assert wait(lambda: tab._list.count() == 2)
    assert tab._go.isEnabled()


def test_check_dialog_runs_both_steps(app_parts, wait, monkeypatch):
    settings, _manager, _loader = app_parts
    monkeypatch.setattr("firedownload.ui.check_dialog.find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    dialog = CheckDialog(settings)
    dialog._run.click()
    assert wait(lambda: "2/2 Descarga real" in dialog._report.toPlainText() and dialog._run.isEnabled())
    assert "→ Resultado: OK. Archivos:" in dialog._report.toPlainText()
    assert "→ Conversión con FFmpeg: OK" in dialog._report.toPlainText()
    dialog.reject()


def test_check_dialog_skips_an_unavailable_test_video(app_parts, wait, monkeypatch):
    settings, _manager, _loader = app_parts
    monkeypatch.setenv("FAKE_YTDLP_UNAVAILABLE", "jNQXAC9IAdw")
    monkeypatch.setattr("firedownload.ui.check_dialog.find_ffmpeg", lambda: None)
    dialog = CheckDialog(settings)
    dialog._run.click()
    assert wait(lambda: "→ Resultado: OK. Archivos:" in dialog._report.toPlainText() and dialog._run.isEnabled())
    report = dialog._report.toPlainText()
    assert "probando otro" in report and "BaW_jenozKc" in report
    dialog.reject()


def test_download_card_shows_activity_before_first_progress(app_parts, wait, monkeypatch):
    settings, manager, loader = app_parts
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    tab = DownloadTab(settings, manager, loader)
    tab._url.setText(VIDEO)
    tab._add.click()
    item = next(iter(manager.items.values()))
    assert tab._cards[item.id]._state.text() in ("Iniciando…", "Obteniendo información…")


def test_about_dialog_shows_versions(app_parts, wait):
    import firedownload

    settings, _manager, _loader = app_parts
    dialog = AboutDialog(settings)
    assert wait(lambda: dialog._values["yt-dlp"].text() == "2099.01.01")
    text = dialog.info_text()
    assert firedownload.__version__ in text and "yt-dlp: 2099.01.01" in text
    assert firedownload.__github__ in text and firedownload.__site_web__ in text
    dialog.reject()


def test_menu_has_about_with_f1_and_tab_shortcuts(app_parts):
    settings, manager, loader = app_parts
    window = MainWindow(settings, manager, loader)
    shortcuts = {a.text(): a.shortcut().toString() for a in window.findChildren(QAction)}
    assert shortcuts["Acerca de FireDownload"] == "F1"
    assert shortcuts["Buscar"] == "Ctrl+2" and shortcuts["Salir"] == "Ctrl+Q"


def test_window_remembers_size_and_tab(app_parts):
    from firedownload.config import Settings

    settings, manager, loader = app_parts
    window = MainWindow(settings, manager, loader)
    window.resize(1000, 650)
    window._tabs.setCurrentIndex(2)
    window._remember_layout()
    saved = Settings.load()
    assert saved.window_size == [1000, 650] and saved.last_tab == 2


def test_low_disk_space_asks_before_downloading(app_parts, monkeypatch):
    settings, manager, loader = app_parts
    monkeypatch.setattr("firedownload.ui.download_tab.free_space", lambda _path: 1024)
    asked = []
    monkeypatch.setattr(
        "firedownload.ui.download_tab.QMessageBox.question",
        lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No,
    )
    tab = DownloadTab(settings, manager, loader)
    assert tab.add_urls([VIDEO]) == 0 and asked and not manager.items


def test_about_dialog_has_author_tab(app_parts):
    from PySide6.QtWidgets import QTabWidget

    settings, _manager, _loader = app_parts
    dialog = AboutDialog(settings)
    tabs = dialog.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Programa", "Sobre el autor"]
    dialog.reject()


def test_banner_lists_missing_tools(app_parts, monkeypatch):
    settings, manager, loader = app_parts
    monkeypatch.setattr("firedownload.ui.download_tab.check_ffmpeg", lambda: False)
    monkeypatch.setattr("firedownload.ui.download_tab.find_js_runtime", lambda: None)
    tab = DownloadTab(settings, manager, loader)
    assert not tab._banner.isHidden()
    assert "FFmpeg" in tab._banner_label.text() and "Deno" in tab._banner_label.text()
    monkeypatch.setattr("firedownload.ui.download_tab.check_ffmpeg", lambda: True)
    monkeypatch.setattr("firedownload.ui.download_tab.find_js_runtime", lambda: ("deno", "/x"))
    tab.refresh_banner()
    assert tab._banner.isHidden()


def test_profile_applies_visible_options_and_extras_to_the_download(app_parts):
    settings, manager, loader = app_parts
    tab = DownloadTab(settings, manager, loader)
    tab._profile.setCurrentIndex(tab._profile.findData("Música · MP3 con carátula"))
    assert tab._audio_only.isChecked() and tab._audio_format.currentText() == "mp3"
    tab._url.setText(VIDEO)
    tab._add.click()
    options = next(iter(manager.items.values())).options
    assert options["audio_only"] is True and options["embed_thumbnail"] is True and options["embed_metadata"] is True


def test_custom_profile_can_be_saved_and_deleted(app_parts, monkeypatch):
    settings, manager, loader = app_parts
    monkeypatch.setattr("firedownload.ui.download_tab.QInputDialog.getText", lambda *a, **k: ("Mi perfil", True))
    tab = DownloadTab(settings, manager, loader)
    tab._quality.setCurrentText("720p")
    tab._profile_save.click()
    assert "Mi perfil" in settings.profiles and tab._profile.currentData() == "Mi perfil"
    assert tab._profile_delete.isEnabled()
    tab._profile_delete.click()
    assert "Mi perfil" not in settings.profiles


def test_queue_buttons_reorder_cards(app_parts, wait, monkeypatch):
    settings, manager, loader = app_parts
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    settings.max_concurrent = 1
    tab = DownloadTab(settings, manager, loader)
    for i in range(3):
        manager.add(VIDEO + f"&n={i}")
    ids = list(manager.items)
    manager.move(ids[2], -1)
    layout = tab._cards_layout
    order = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget() in tab._cards.values()]
    assert [next(k for k, v in tab._cards.items() if v is w) for w in order] == list(manager.items)


def test_info_dialog_builds_sections_from_range_and_chapters(app_parts, wait):
    settings, _manager, loader = app_parts
    dialog = InfoDialog(VIDEO, settings, loader)
    assert wait(lambda: dialog.info is not None)
    dialog._cut_start.setText("1:00")
    dialog._cut_end.setText("2:30")
    assert dialog.options()["sections"] == ["*60-150"]
    dialog._cut_end.setText("")
    assert dialog.options()["sections"] == ["*60-inf"]
    dialog.reject()


def test_tools_dialog_lists_the_three_tools(app_parts):
    from firedownload.ui.tools_dialog import ToolsDialog

    dialog = ToolsDialog()
    assert [row._name for row in dialog._rows] == ["yt-dlp", "ffmpeg", "deno"]
    dialog.reject()
