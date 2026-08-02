from __future__ import annotations

import asyncio
import os
import socket
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

from app.relay_runtime import configure_runtime_environment
from app.websocket_agent_client import WebSocketAgentClient


class GastrodomWebSocketAgentService(
    win32serviceutil.ServiceFramework
):
    _svc_name_ = "GastrodomRelayAgent"
    _svc_display_name_ = "Restaurant OS Relay Agent"
    _svc_description_ = (
        "Безопасное исходящее WebSocket-подключение "
        "TillyPad к Restaurant OS."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.loop = None
        self.task = None
        self.thread = None
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(
            f"{self._svc_name_}: служба запускается"
        )
        try:
            self.main()
        except Exception as exc:
            servicemanager.LogErrorMsg(
                f"{self._svc_name_}: ошибка: {exc}"
            )
            raise

    def _worker(self):
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

    def main(self):
        configure_runtime_environment()
        self.thread = threading.Thread(
            target=self._worker,
            name="RestaurantOSWebSocketAgent",
            daemon=True,
        )
        self.thread.start()

        win32event.WaitForSingleObject(
            self.stop_event,
            win32event.INFINITE,
        )

        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)
        if self.thread:
            self.thread.join(timeout=30)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(
        GastrodomWebSocketAgentService
    )
