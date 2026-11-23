"""Notificaciones del sistema sin dependencias extra (notify-send, osascript, PowerShell)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

_POWERSHELL_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
    "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$text = $xml.GetElementsByTagName('text');"
    "$text.Item(0).AppendChild($xml.CreateTextNode($env:FD_TITLE)) | Out-Null;"
    "$text.Item(1).AppendChild($xml.CreateTextNode($env:FD_MSG)) | Out-Null;"
    "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))"
)


def command_for(title: str, message: str, platform_name: str | None = None) -> tuple[list[str], dict[str, str]] | None:
    """Comando y variables de entorno para notificar en esta plataforma, o None si no hay forma."""
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        shell = shutil.which("powershell") or "powershell"
        return (
            [shell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", _POWERSHELL_TOAST],
            {"FD_TITLE": title, "FD_MSG": message},
        )
    if platform_name == "darwin":
        script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run"]
        return ["osascript", *script, "--", title, message], {}
    if shutil.which("notify-send"):
        return ["notify-send", "-a", "FireDownload", "--", title, message], {}
    return None


def send(title: str, message: str) -> None:
    """Muestra una notificación; si no es posible, no hace nada."""
    command = command_for(title, message)
    if command is None:
        return
    argv, extra_env = command
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        subprocess.Popen(
            argv,
            env={**os.environ, **extra_env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **extra,
        )
    except OSError as exc:
        log.debug("No se pudo mostrar la notificación: %s", exc)
