from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from app.websocket_agent_client import WebSocketAgentClient


SERVICE_NAME = "GastrodomRelayAgent"


def data_dir() -> Path:
    root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(root) / "Gastrodom" / "RelayAgent"


def configure_environment() -> None:
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "logs").mkdir(exist_ok=True)
    (directory / "cache").mkdir(exist_ok=True)

    os.environ["GASTRODOM_ENV_FILE"] = str(directory / "agent.env")
    os.environ.setdefault(
        "TILLYPAD_RELAY_CACHE_DIR",
        str(directory / "cache"),
    )
    os.chdir(directory)


class GastrodomRelayAgentService(
    win32serviceutil.ServiceFramework
):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "Restaurant OS Relay Agent"
    _svc_description_ = (
        "Безопасное исходящее WebSocket-подключение "
        "TillyPad к Restaurant OS."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.thread: threading.Thread | None = None
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.loop is not None and self.task is not None:
            self.loop.call_soon_threadsafe(self.task.cancel)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        configure_environment()
        servicemanager.LogInfoMsg(
            f"{SERVICE_NAME}: служба запускается"
        )
        try:
            self.thread = threading.Thread(
                target=self._run_agent,
                name="RestaurantOSAgent",
                daemon=True,
            )
            self.thread.start()

            win32event.WaitForSingleObject(
                self.stop_event,
                win32event.INFINITE,
            )

            if self.loop is not None and self.task is not None:
                self.loop.call_soon_threadsafe(self.task.cancel)
            if self.thread is not None:
                self.thread.join(timeout=30)
        except Exception as exc:
            servicemanager.LogErrorMsg(
                f"{SERVICE_NAME}: ошибка: {exc}"
            )
            raise

    def _run_agent(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.task = self.loop.create_task(
            WebSocketAgentClient().run_forever()
        )
        try:
            self.loop.run_until_complete(self.task)
        except asyncio.CancelledError:
            pass
        finally:
            self.loop.close()


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(
        GastrodomRelayAgentService
    )
