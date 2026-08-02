from __future__ import annotations

import os
import socket
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil


class GastrodomWebSocketGatewayService(
    win32serviceutil.ServiceFramework
):
    _svc_name_ = "GastrodomWebSocketGateway"
    _svc_display_name_ = "Gastrodom WebSocket Gateway"
    _svc_description_ = (
        "Промежуточный WebSocket-шлюз между Restaurant OS "
        "и агентами TillyPad."
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

    def main(self):
        import uvicorn

        host = os.environ.get("WS_GATEWAY_HOST", "0.0.0.0")
        port = int(os.environ.get("WS_GATEWAY_PORT", "8020"))

        config = uvicorn.Config(
            "app.websocket_gateway:app",
            host=host,
            port=port,
            reload=False,
            access_log=False,
            log_level="info",
        )
        self.server = uvicorn.Server(config)

        self.server_thread = threading.Thread(
            target=self.server.run,
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
        GastrodomWebSocketGatewayService
    )
