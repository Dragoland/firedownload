"""Instancia única: una segunda ejecución avisa a la primera (y le pasa URLs) y termina."""

from __future__ import annotations

import getpass
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)


def default_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"FireDownload-{user}"


class SingleInstance(QObject):
    """Servidor local en la primera instancia; las siguientes le envían un mensaje."""

    message_received = Signal(str)

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name or default_name()
        self._server: QLocalServer | None = None

    def send_to_running(self, message: str) -> bool:
        """Envía el mensaje a la instancia ya abierta; False si no hay ninguna."""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(500):
            return False
        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return True

    def listen(self) -> bool:
        """Empieza a escuchar a otras instancias."""
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        ok = self._server.listen(self._name)
        if not ok:
            log.warning("No se pudo abrir el canal de instancia única: %s", self._server.errorString())
        return ok

    def _on_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        if socket.bytesAvailable() or socket.waitForReadyRead(500):
            data = bytes(socket.readAll()).decode("utf-8", "replace")
            self.message_received.emit(data)
        socket.disconnectFromServer()
        socket.deleteLater()
