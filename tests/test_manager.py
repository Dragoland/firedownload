"""DownloadManager: cola, concurrencia, pausa, persistencia y reintento."""

import pytest

pytest.importorskip("PySide6.QtCore")
pytest.importorskip("psutil")

from firedownload.core import history, queue_store  # noqa: E402
from firedownload.core.manager import DownloadManager, Status  # noqa: E402

URL = "https://www.youtube.com/watch?v=aaaaaaaaaaa"


def test_download_completes_and_is_recorded(fake_ytdlp, settings, wait):
    manager = DownloadManager(settings)
    item = manager.add(URL, title="Mi título", thumbnail="th")
    assert wait(lambda: item.status is Status.COMPLETED)
    assert item.title == "Mi título" and item.progress == 100
    assert [e["title"] for e in history.load()] == ["Mi título"]
    assert queue_store.load() == [], "lo terminado no se guarda en la cola"


def test_concurrency_limit_and_pause_frees_a_slot(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.2")
    settings.max_concurrent = 1
    manager = DownloadManager(settings)
    first = manager.add(URL)
    second = manager.add(URL + "&b=1")
    assert len(manager.active) == 1 and len(manager.queue) == 1
    assert wait(lambda: first.progress > 0)
    manager.pause(first.id)
    assert first.status is Status.PAUSED and second.status is Status.DOWNLOADING
    manager.resume(first.id)
    assert wait(lambda: first.finished and second.finished, timeout=60)
    assert first.status is Status.COMPLETED and second.status is Status.COMPLETED


def test_queue_is_persisted_and_restored_as_pending(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    manager = DownloadManager(settings)
    manager.add(URL, title="Pendiente")
    saved = queue_store.load()
    assert [e["title"] for e in saved] == ["Pendiente"]
    manager.shutdown()

    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.01")
    fresh = DownloadManager(settings)
    assert fresh.restore() == 1
    item = next(iter(fresh.items.values()))
    assert item.status is Status.PENDING and not fresh.active
    fresh.resume_pending()
    assert wait(lambda: item.status is Status.COMPLETED)


def test_restore_sanitizes_tampered_options(fake_ytdlp, settings):
    queue_store.save([{"url": URL, "options": {"speed_limit": "--exec rm", "retries": 99}}])
    manager = DownloadManager(settings)
    manager.restore()
    options = next(iter(manager.items.values())).options
    assert options["speed_limit"] == "" and options["retries"] == 10


def test_failed_item_keeps_diagnostics_and_can_retry(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_FAIL", "1")
    manager = DownloadManager(settings)
    item = manager.add(URL)
    assert wait(lambda: item.status is Status.FAILED)
    assert "anti-bots" in item.error_message and "ERROR" in item.details
    monkeypatch.setenv("FAKE_YTDLP_FAIL", "0")
    manager.retry(item.id)
    assert item.id not in manager.items and len(manager.items) == 1
    new_item = next(iter(manager.items.values()))
    assert wait(lambda: new_item.status is Status.COMPLETED)


def test_cancel_queued_item(fake_ytdlp, settings, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    settings.max_concurrent = 1
    manager = DownloadManager(settings)
    manager.add(URL)
    queued = manager.add(URL + "&b=1")
    manager.cancel(queued.id)
    assert queued.status is Status.CANCELLED and not manager.queue
    manager.shutdown()


def test_empty_run_is_reported_as_failed_not_completed(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_EMPTY", "1")
    manager = DownloadManager(settings)
    item = manager.add(URL)
    assert wait(lambda: item.finished)
    assert item.status is Status.FAILED and "sin descargar" in item.error_message
    assert history.load() == []


def test_phase_is_shown_then_cleared_by_progress(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.2")
    manager = DownloadManager(settings)
    item = manager.add(URL)
    assert wait(lambda: item.progress > 0)
    assert item.phase == ""
    manager.shutdown()


def test_pause_all_resume_all_and_total_speed(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    manager = DownloadManager(settings)
    a, b = manager.add(URL), manager.add(URL + "&b=1")
    assert wait(lambda: a.speed and b.speed)
    assert manager.total_speed() == 2 * 1024**2
    manager.pause_all()
    assert a.status is Status.PAUSED and b.status is Status.PAUSED and not manager.active
    assert manager.total_speed() == 0
    manager.resume_all()
    assert a.status is Status.DOWNLOADING and b.status is Status.DOWNLOADING
    manager.shutdown()


def test_reorder_queue_and_prioritize(fake_ytdlp, settings, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    settings.max_concurrent = 1
    manager = DownloadManager(settings)
    running = manager.add(URL)
    a, b, c = (manager.add(URL + f"&n={i}") for i in range(3))
    orders = []
    manager.order_changed.connect(lambda: orders.append(1))
    assert [i.id for i in manager.queue] == [a.id, b.id, c.id]
    manager.move(c.id, -1)
    assert [i.id for i in manager.queue] == [a.id, c.id, b.id]
    assert list(manager.items) == [running.id, a.id, c.id, b.id], "items refleja el orden de la cola"
    manager.prioritize(b.id)
    assert [i.id for i in manager.queue] == [b.id, a.id, c.id]
    manager.move(b.id, -5)
    manager.move(running.id, 1)
    assert [i.id for i in manager.queue] == [b.id, a.id, c.id] and orders
    manager.shutdown()


def test_archive_skip_completes_without_history(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_ARCHIVE_SKIP", "1")
    manager = DownloadManager(settings)
    item = manager.add(URL, {**settings.download_options(), "use_archive": True})
    assert wait(lambda: item.finished)
    assert item.status is Status.COMPLETED and history.load() == []
