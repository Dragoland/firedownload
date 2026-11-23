"""Instancia única: la segunda ejecución entrega su mensaje a la primera."""

import pytest

pytest.importorskip("PySide6.QtNetwork")

from firedownload.core.single_instance import SingleInstance  # noqa: E402


def test_second_instance_sends_its_message(qapp, wait):
    name = "FireDownload-test-instance"
    first = SingleInstance(name)
    assert first.listen()
    received = []
    first.message_received.connect(received.append)
    second = SingleInstance(name)
    assert second.send_to_running("SHOW\nhttps://example.com/v")
    assert wait(lambda: received)
    assert received[0].splitlines() == ["SHOW", "https://example.com/v"]


def test_no_running_instance(qapp):
    assert not SingleInstance("FireDownload-test-nadie").send_to_running("SHOW")
