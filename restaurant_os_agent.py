from __future__ import annotations

import asyncio
import ctypes
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import servicemanager
import win32api
import win32event
import win32service
import win32serviceutil
import win32security
import pywintypes

from app.agent_diagnostics import (
    export_support_report,
    load_env_file,
    run_all,
)
from app.websocket_agent_client import WebSocketAgentClient


APP_NAME = "Restaurant OS Agent"
VERSION = "15.6.0"
SERVICE_NAME = "RestaurantOSAgent"
SERVICE_DISPLAY_NAME = "Restaurant OS Agent"

INSTALL_DIR = Path(
    os.environ.get("ProgramFiles", r"C:\Program Files")
) / "RestaurantOS"
DATA_DIR = INSTALL_DIR / "data"
INSTALLED_EXE = INSTALL_DIR / "RestaurantOSAgent.exe"
ENV_FILE = DATA_DIR / "agent.env"


DEFAULTS = {
    "TILLYPAD_SQL_SERVER": "127.0.0.1",
    "TILLYPAD_SQL_PORT": "1433",
    "TILLYPAD_SQL_DATABASE": "TillypadSegment",
    "TILLYPAD_SQL_USER": "",
    "TILLYPAD_SQL_PASSWORD": "",
    "TILLYPAD_SQL_DRIVER": "ODBC Driver 18 for SQL Server",
    "TILLYPAD_SQL_ENCRYPT": "no",
    "TILLYPAD_SQL_TRUST_CERTIFICATE": "yes",
    "TILLYPAD_SQL_TIMEOUT": "10",
    "TILLYPAD_AGENT_ID": os.environ.get(
        "COMPUTERNAME",
        "restaurant-main",
    ).lower(),
    "TILLYPAD_WS_GATEWAY_URL": (
        "wss://gateway.example.ru/ws/agent"
    ),
    "TILLYPAD_WS_API_KEY": "",
    "TILLYPAD_WS_HEARTBEAT": "20",
    "TILLYPAD_WS_RECONNECT_MAX": "60",
}


FIELDS = [
    ("TILLYPAD_SQL_SERVER", "SQL Server"),
    ("TILLYPAD_SQL_PORT", "SQL порт"),
    ("TILLYPAD_SQL_DATABASE", "База данных"),
    ("TILLYPAD_SQL_USER", "SQL логин"),
    ("TILLYPAD_SQL_PASSWORD", "SQL пароль"),
    ("TILLYPAD_SQL_DRIVER", "ODBC-драйвер"),
    ("TILLYPAD_AGENT_ID", "Agent ID"),
    ("TILLYPAD_WS_GATEWAY_URL", "WebSocket Gateway"),
    ("TILLYPAD_WS_API_KEY", "API-ключ"),
]


def configure_environment() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "logs").mkdir(exist_ok=True)
    (DATA_DIR / "cache").mkdir(exist_ok=True)

    os.environ["GASTRODOM_ENV_FILE"] = str(ENV_FILE)
    os.environ.setdefault(
        "TILLYPAD_RELAY_CACHE_DIR",
        str(DATA_DIR / "cache"),
    )
    os.chdir(DATA_DIR)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(arguments: list[str]) -> None:
    params = " ".join(
        [f'"{sys.executable}"']
        + [f'"{argument}"' for argument in arguments]
    )
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        " ".join(f'"{arg}"' for arg in arguments),
        None,
        1,
    )
    if result <= 32:
        raise RuntimeError(
            "Не удалось запросить права администратора."
        )


def run_hidden(
    command: list[str],
    check: bool = True,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
        creationflags=getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0,
        ),
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            (result.stdout + "\n" + result.stderr).strip()
            or f"Код ошибки: {result.returncode}"
        )
    return result


def write_default_env() -> None:
    if ENV_FILE.exists():
        return
    lines = [
        "# Restaurant OS Agent",
        f"# Version {VERSION}",
        "",
    ]
    values = dict(DEFAULTS)
    if not values["TILLYPAD_WS_API_KEY"]:
        values["TILLYPAD_WS_API_KEY"] = secrets.token_urlsafe(48)
    lines.extend(f"{key}={value}" for key, value in values.items())
    ENV_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


class RestaurantOSAgentService(
    win32serviceutil.ServiceFramework
):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = (
        "Безопасное исходящее WebSocket-подключение "
        "TillyPad к Restaurant OS."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(
            None,
            0,
            0,
            None,
        )
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.thread: threading.Thread | None = None
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(
            win32service.SERVICE_STOP_PENDING
        )
        if self.loop is not None and self.task is not None:
            self.loop.call_soon_threadsafe(self.task.cancel)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        configure_environment()
        servicemanager.LogInfoMsg(
            f"{SERVICE_NAME}: запуск v{VERSION}"
        )

        self.thread = threading.Thread(
            target=self._run_agent,
            name="RestaurantOSWebSocketAgent",
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


def run_service_dispatcher() -> None:
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(
        RestaurantOSAgentService
    )
    servicemanager.StartServiceCtrlDispatcher()


def _open_service_manager(access: int):
    return win32service.OpenSCManager(None, None, access)


def _stop_and_delete_existing_service() -> None:
    manager = _open_service_manager(win32service.SC_MANAGER_CONNECT)
    try:
        try:
            service = win32service.OpenService(
                manager,
                SERVICE_NAME,
                win32service.SERVICE_STOP | win32service.DELETE | win32service.SERVICE_QUERY_STATUS,
            )
        except pywintypes.error as exc:
            if exc.winerror == 1060:
                return
            raise
        try:
            try:
                status = win32service.QueryServiceStatus(service)
                if status[1] != win32service.SERVICE_STOPPED:
                    try:
                        win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
                    except pywintypes.error as exc:
                        if exc.winerror not in (1062, 1052):
                            raise
                    deadline = time.time() + 15
                    while time.time() < deadline:
                        if win32service.QueryServiceStatus(service)[1] == win32service.SERVICE_STOPPED:
                            break
                        time.sleep(0.5)
            finally:
                win32service.DeleteService(service)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)
    time.sleep(1)


def register_service() -> None:
    if not is_admin():
        raise PermissionError("Для регистрации службы нужны права администратора.")
    _stop_and_delete_existing_service()
    manager = _open_service_manager(win32service.SC_MANAGER_CREATE_SERVICE)
    service = None
    try:
        binary_path = f'"{INSTALLED_EXE}" --run-service'
        service = win32service.CreateService(
            manager,
            SERVICE_NAME,
            SERVICE_DISPLAY_NAME,
            win32service.SERVICE_ALL_ACCESS,
            win32service.SERVICE_WIN32_OWN_PROCESS,
            win32service.SERVICE_AUTO_START,
            win32service.SERVICE_ERROR_NORMAL,
            binary_path,
            None,
            0,
            None,
            None,
            None,
        )
        win32service.ChangeServiceConfig2(
            service,
            win32service.SERVICE_CONFIG_DESCRIPTION,
            "Безопасное исходящее WebSocket-подключение TillyPad к Restaurant OS.",
        )
        win32service.ChangeServiceConfig2(
            service,
            win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
            {
                "ResetPeriod": 86400,
                "RebootMsg": "",
                "Command": "",
                "Actions": [
                    (win32service.SC_ACTION_RESTART, 5000),
                    (win32service.SC_ACTION_RESTART, 15000),
                    (win32service.SC_ACTION_RESTART, 60000),
                ],
            },
        )
        try:
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, True)
        except (AttributeError, pywintypes.error):
            pass
        win32service.StartService(service, None)
    finally:
        if service is not None:
            win32service.CloseServiceHandle(service)
        win32service.CloseServiceHandle(manager)


def grant_data_permissions() -> None:
    """
    Рабочие данные хранятся рядом с приложением.
    Запись разрешена службе SYSTEM и администраторам.
    Панель настроек всегда запускается с повышением прав.
    """
    grants = [
        "*S-1-5-18:(OI)(CI)F",
        "*S-1-5-32-544:(OI)(CI)F",
    ]

    run_hidden(
        ["takeown", "/F", str(INSTALL_DIR), "/A", "/R", "/D", "Y"],
        check=False,
    )
    run_hidden(
        ["icacls", str(INSTALL_DIR), "/inheritance:e", "/T", "/C"],
        check=False,
    )

    for grant in grants:
        result = run_hidden(
            [
                "icacls",
                str(INSTALL_DIR),
                "/grant:r",
                grant,
                "/T",
                "/C",
            ],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Не удалось назначить права каталогу:\n"
                + (result.stdout + result.stderr)
            )

def install_files() -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    grant_data_permissions()

    configure_environment()
    write_default_env()

    current_exe = Path(sys.executable).resolve()
    installed_resolved = INSTALLED_EXE.resolve()

    if current_exe != installed_resolved:
        shutil.copy2(current_exe, INSTALLED_EXE)

    run_hidden(
        ["attrib", "+h", str(DATA_DIR)],
        check=False,
    )
    grant_data_permissions()

    register_service()


def uninstall_agent() -> None:
    if not is_admin():
        relaunch_as_admin(["--uninstall"])
        return
    try:
        _stop_and_delete_existing_service()

        # Старый каталог предыдущих версий больше не используется.
        legacy_dir = Path(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        ) / "RestaurantOS"
        if legacy_dir.exists():
            run_hidden(
                ["takeown", "/F", str(legacy_dir), "/A", "/R", "/D", "Y"],
                check=False,
            )
            shutil.rmtree(legacy_dir, ignore_errors=True)
    except Exception as exc:
        messagebox.showerror(APP_NAME, f"Не удалось удалить службу:\n{exc}")
        return
    messagebox.showinfo(APP_NAME, "Служба удалена.\n\nНастройки в ProgramData сохранены.")


class SetupWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — установка")
        self.geometry("720x500")
        self.resizable(False, False)
        self.progress = tk.DoubleVar(value=0)
        self.status = tk.StringVar(
            value="Готово к установке"
        )
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=30)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=APP_NAME,
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=(
                "Один файл для установки, службы "
                "и настройки подключения TillyPad"
            ),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(6, 22))

        box = ttk.LabelFrame(
            frame,
            text="Будет выполнено",
            padding=18,
        )
        box.pack(fill="x")

        for text in (
            "Установка одного RestaurantOSAgent.exe",
            "Регистрация скрытой службы Windows",
            "Автоматический запуск вместе с Windows",
            "Создание защищённой конфигурации",
            "Открытие панели первичной настройки",
        ):
            ttk.Label(
                box,
                text=f"✓  {text}",
            ).pack(anchor="w", pady=4)

        ttk.Progressbar(
            frame,
            variable=self.progress,
            maximum=100,
        ).pack(fill="x", pady=(24, 8))

        ttk.Label(
            frame,
            textvariable=self.status,
        ).pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(25, 0))

        self.install_button = ttk.Button(
            buttons,
            text="Установить",
            command=self.install,
        )
        self.install_button.pack(side="right")

        ttk.Button(
            buttons,
            text="Отмена",
            command=self.destroy,
        ).pack(side="right", padx=10)

    def stage(self, value: int, text: str):
        self.progress.set(value)
        self.status.set(text)
        self.update_idletasks()

    def install(self):
        self.install_button.configure(state="disabled")
        try:
            if not is_admin():
                relaunch_as_admin(["--setup"])
                self.destroy()
                return

            self.stage(15, "Подготовка каталогов...")
            configure_environment()

            self.stage(35, "Копирование приложения...")
            install_files()

            self.stage(80, "Проверка запуска службы Windows...")
            self.stage(100, "Установка завершена")
            messagebox.showinfo(
                APP_NAME,
                (
                    "Restaurant OS Agent установлен.\n\n"
                    "Открывается панель настройки."
                ),
            )

            subprocess.Popen(
                [str(INSTALLED_EXE), "--config"],
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )
            self.destroy()
        except Exception as exc:
            self.status.set("Ошибка установки")
            self.install_button.configure(state="normal")
            messagebox.showerror(APP_NAME, str(exc))


class ConfigWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — настройки")
        self.geometry("930x700")
        self.minsize(840, 620)

        self.variables: dict[str, tk.StringVar] = {}
        self.results = []
        self.status = tk.StringVar(value="Готово")
        self.service_status = tk.StringVar(
            value="Проверка службы..."
        )

        self._build()
        self._load()
        self.refresh_service()

    def _build(self):
        header = ttk.Frame(self, padding=18)
        header.pack(fill="x")

        ttk.Label(
            header,
            text=APP_NAME,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=f"Версия {VERSION}",
        ).pack(anchor="w")

        body = ttk.Frame(
            self,
            padding=(18, 0, 18, 18),
        )
        body.pack(fill="both", expand=True)

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        settings = ttk.Frame(notebook, padding=16)
        diagnostics = ttk.Frame(notebook, padding=16)
        service = ttk.Frame(notebook, padding=16)

        notebook.add(settings, text="Настройки")
        notebook.add(diagnostics, text="Диагностика")
        notebook.add(service, text="Служба")

        for row, (key, label) in enumerate(FIELDS):
            ttk.Label(
                settings,
                text=label,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=6,
            )

            var = tk.StringVar()
            self.variables[key] = var
            show = (
                "*"
                if "PASSWORD" in key or "API_KEY" in key
                else ""
            )

            ttk.Entry(
                settings,
                textvariable=var,
                show=show,
                width=68,
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=6,
            )

        settings.columnconfigure(1, weight=1)

        controls = ttk.Frame(settings)
        controls.grid(
            row=len(FIELDS),
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 0),
        )

        ttk.Button(
            controls,
            text="Сохранить",
            command=self.save,
        ).pack(side="left")

        ttk.Button(
            controls,
            text="Новый API-ключ",
            command=self.generate_key,
        ).pack(side="left", padx=8)

        ttk.Button(
            controls,
            text="Сохранить и проверить",
            command=self.run_diagnostics,
        ).pack(side="left")

        self.tree = ttk.Treeview(
            diagnostics,
            columns=("status", "result", "time"),
            show="headings",
        )
        self.tree.heading("status", text="Статус")
        self.tree.heading("result", text="Результат")
        self.tree.heading("time", text="Время")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("result", width=600)
        self.tree.column("time", width=100, anchor="center")
        self.tree.pack(fill="both", expand=True)

        diag_controls = ttk.Frame(diagnostics)
        diag_controls.pack(fill="x", pady=(12, 0))

        ttk.Button(
            diag_controls,
            text="Запустить диагностику",
            command=self.run_diagnostics,
        ).pack(side="left")

        ttk.Button(
            diag_controls,
            text="Сохранить отчёт",
            command=self.export_report,
        ).pack(side="left", padx=8)

        ttk.Label(
            service,
            textvariable=self.service_status,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", pady=(0, 16))

        service_controls = ttk.Frame(service)
        service_controls.pack(anchor="w")

        for caption, action in (
            ("Запустить", "start"),
            ("Остановить", "stop"),
            ("Перезапустить", "restart"),
        ):
            ttk.Button(
                service_controls,
                text=caption,
                command=lambda value=action: (
                    self.service_action(value)
                ),
            ).pack(side="left", padx=(0, 8))

        ttk.Button(
            service_controls,
            text="Удалить службу",
            command=uninstall_agent,
        ).pack(side="left", padx=(15, 0))

        footer = ttk.Frame(self, padding=(18, 8))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            textvariable=self.status,
        ).pack(anchor="w")

    def collect(self) -> dict[str, str]:
        result = dict(DEFAULTS)
        for key, variable in self.variables.items():
            result[key] = variable.get().strip()
        return result

    def _load(self):
        values = dict(DEFAULTS)
        values.update(load_env_file(ENV_FILE))
        for key, _ in FIELDS:
            self.variables[key].set(values.get(key, ""))

    def save(self, show_message: bool = True):
        configure_environment()
        values = self.collect()
        lines = [
            "# Restaurant OS Agent",
            f"# Version {VERSION}",
            "",
        ]
        lines.extend(
            f"{key}={value}"
            for key, value in values.items()
        )
        ENV_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        self.status.set("Настройки сохранены")

        if show_message:
            messagebox.showinfo(
                APP_NAME,
                "Настройки сохранены.",
            )

    def generate_key(self):
        self.variables[
            "TILLYPAD_WS_API_KEY"
        ].set(secrets.token_urlsafe(48))

    def run_diagnostics(self):
        self.save(show_message=False)
        self.status.set("Выполняется диагностика...")
        threading.Thread(
            target=self._diagnostics_worker,
            daemon=True,
        ).start()

    def _diagnostics_worker(self):
        results = run_all(self.collect())
        self.results = results
        self.after(
            0,
            lambda: self.show_results(results),
        )

    def show_results(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for result in results:
            self.tree.insert(
                "",
                "end",
                values=(
                    "Успешно" if result.ok else "Ошибка",
                    f"{result.name}: {result.message}",
                    f"{result.duration_ms} мс",
                ),
            )

        count = sum(1 for result in results if result.ok)
        self.status.set(
            f"Диагностика: {count}/{len(results)} успешно"
        )

    def export_report(self):
        if not self.results:
            messagebox.showwarning(
                APP_NAME,
                "Сначала запустите диагностику.",
            )
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not filename:
            return

        export_support_report(
            self.collect(),
            self.results,
            Path(filename),
        )
        messagebox.showinfo(
            APP_NAME,
            "Отчёт сохранён.",
        )

    def refresh_service(self):
        result = run_hidden(
            ["sc.exe", "query", SERVICE_NAME],
            check=False,
        )
        text = (result.stdout + result.stderr).upper()

        if "RUNNING" in text:
            value = "Служба запущена"
        elif "STOPPED" in text:
            value = "Служба остановлена"
        else:
            value = "Служба не установлена"

        self.service_status.set(value)

    def service_action(self, action: str):
        if action == "restart":
            run_hidden(
                ["sc.exe", "stop", SERVICE_NAME],
                check=False,
            )
            time.sleep(1)
            run_hidden(
                ["sc.exe", "start", SERVICE_NAME],
                check=False,
            )
        else:
            run_hidden(
                ["sc.exe", action, SERVICE_NAME],
                check=False,
            )

        self.after(1200, self.refresh_service)


def main() -> None:
    args = set(sys.argv[1:])

    if "--run-service" in args:
        configure_environment()
        run_service_dispatcher()
        return

    if "--config" in args:
        if not is_admin():
            relaunch_as_admin(["--config"])
            return
        configure_environment()
        ConfigWindow().mainloop()
        return

    if "--uninstall" in args:
        uninstall_agent()
        return

    if not is_admin():
        relaunch_as_admin(["--setup"])
        return

    SetupWindow().mainloop()


if __name__ == "__main__":
    main()
