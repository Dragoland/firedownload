"""Configuración común: datos aislados en una carpeta temporal y yt-dlp falso."""

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

_HOME = tempfile.mkdtemp(prefix="firedownload-test-")
for _var in ("HOME", "USERPROFILE", "APPDATA"):
    os.environ[_var] = _HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAKE = Path(__file__).with_name("fake_ytdlp.py")


@pytest.fixture(autouse=True)
def clean_data():
    from firedownload.config import Paths

    for file in (Paths.HISTORY_FILE, Paths.QUEUE_FILE, Paths.CONFIG_FILE):
        file.unlink(missing_ok=True)


@pytest.fixture
def fake_ytdlp(monkeypatch):
    """Sustituye yt-dlp por el falso en todos los módulos de la aplicación."""
    command = (sys.executable, str(FAKE))
    for name, module in list(sys.modules.items()):
        if not name.startswith("firedownload"):
            continue
        if hasattr(module, "find_ytdlp"):
            monkeypatch.setattr(module, "find_ytdlp", lambda: command)
        if hasattr(module, "find_js_runtime"):
            monkeypatch.setattr(module, "find_js_runtime", lambda: None)
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.02")
    return command


@pytest.fixture
def settings(tmp_path):
    from firedownload.config import Settings

    return Settings(download_path=str(tmp_path / "downloads"), max_concurrent=2, enable_sounds=False)


@pytest.fixture(scope="session")
def qapp():
    try:
        from PySide6.QtWidgets import QApplication as App
    except ImportError:
        from PySide6.QtCore import QCoreApplication as App
    return App.instance() or App([])


@pytest.fixture
def wait(qapp):
    """wait(condicion, timeout): procesa eventos de Qt hasta que se cumpla la condición."""
    from PySide6.QtCore import QCoreApplication

    def _wait(predicate, timeout: float = 20.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            QCoreApplication.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    return _wait
