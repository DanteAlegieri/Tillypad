from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

from app.relay_runtime import configure_runtime_environment


class GastrodomRelayAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "GastrodomRelayAgent"
    _svc_display_name_ = "Gastrodom Relay Agent"
    _svc_description_ = (
        "Безопасный агент чтения TillyPad SQL Server "
        "для Restaurant OS."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.server_thread = None
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server is not None:
            self.server.should_exit = True
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(
            f"{self._svc_name_}: служба запускается"
        )
        try:
            self.main()
        except Exception as exc:
            servicemanager.LogErrorMsg(
                f"{self._svc_name_}: ошибка запуска: {exc}"
            )
            raise
        finally:
            servicemanager.LogInfoMsg(
                f"{self._svc_name_}: служба остановлена"
            )

    def main(self):
        import uvicorn

        configure_runtime_environment()

        host = os.environ.get("RELAY_AGENT_HOST", "127.0.0.1")
        port = int(os.environ.get("RELAY_AGENT_PORT", "8010"))

        config = uvicorn.Config(
            "app.relay_agent:app",
            host=host,
            port=port,
            reload=False,
            access_log=False,
            log_level="info",
        )
        self.server = uvicorn.Server(config)

        self.server_thread = threading.Thread(
            target=self.server.run,
            name="GastrodomRelayUvicorn",
            daemon=True,
        )
        self.server_thread.start()

        win32event.WaitForSingleObject(
            self.stop_event,
            win32event.INFINITE,
        )

        self.server.should_exit = True
        self.server_thread.join(timeout=30)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(
        GastrodomRelayAgentService
    )
