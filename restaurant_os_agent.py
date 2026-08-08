from __future__ import annotations

import asyncio
import ctypes
import json
import logging
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
    discover_payment_schema,
    export_support_report,
    load_env_file,
    run_all,
    save_payment_schema_report,
)
from app.websocket_agent_client import WebSocketAgentClient
from app.sql_autodetect import (
    find_tillypad,
    installed_odbc_drivers,
)
from app.local_agent_web import LocalAgentWebServer
from app.agent_state import get_runtime_state
from app.agent_config import reload_config
from app.service_manager import (
    install_service,
    query_service,
    remove_service,
    restart_service,
    start_service,
    stop_service,
)


APP_NAME = "Restaurant OS Agent"
VERSION = "31.4.2"
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
        "ws://127.0.0.1:8020/ws/agent"
    ),
    "TILLYPAD_WS_API_KEY": "",
    "TILLYPAD_WS_HEARTBEAT": "20",
    "TILLYPAD_WS_RECONNECT_MAX": "60",
    "TILLYPAD_QUERY_CACHE_TTL": "45",
    "TILLYPAD_QUERY_CACHE_MAX": "256",
    "TILLYPAD_WS_COMPRESS_THRESHOLD": "65536",
    "TILLYPAD_CLOUD_SYNC_SECONDS": "300",
    "RESTAURANTOS_LOCAL_WEB_HOST": "127.0.0.1",
    "RESTAURANTOS_LOCAL_WEB_PORT": "8090",
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
    os.environ["RESTAURANTOS_DATA_DIR"] = str(DATA_DIR)
    reload_config()
    os.environ.setdefault(
        "TILLYPAD_RELAY_CACHE_DIR",
        str(DATA_DIR / "cache"),
    )
    os.chdir(DATA_DIR)


def configure_logging() -> None:
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "agent.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(
        isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    ):
        handler = logging.FileHandler(
            log_path,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | "
                "%(name)s | %(message)s"
            )
        )
        root.addHandler(handler)


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
        self.web_server: LocalAgentWebServer | None = None
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
        configure_logging()
        state = get_runtime_state()
        state.update(
            version=VERSION,
            service_status="running",
        )
        config = reload_config()
        state.update(
            agent_id=config.agent_id,
            gateway_url=config.gateway_url,
        )
        self.web_server = LocalAgentWebServer(
            host=config.local_web_host,
            port=config.local_web_port,
        )
        self.web_server.start()
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
        if self.web_server is not None:
            self.web_server.stop()
        get_runtime_state().update(
            service_status="stopped",
            gateway_status="disconnected",
        )

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

def replace_installed_executable(
    source: Path,
    destination: Path,
    attempts: int = 20,
    delay_seconds: float = 0.5,
) -> None:
    """
    Windows may keep the previous service executable locked briefly
    after stopping/deleting the service. Retry replacement until the
    Service Control Manager and antivirus release the file.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".new.exe")
    backup = destination.with_suffix(".old.exe")

    for path in (temporary, backup):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    shutil.copy2(source, temporary)

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            if destination.exists():
                try:
                    os.replace(destination, backup)
                except FileNotFoundError:
                    pass

            os.replace(temporary, destination)

            try:
                if backup.exists():
                    backup.unlink()
            except OSError:
                # Backup is harmless and can be removed on next update.
                pass
            return

        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            last_error = exc

        time.sleep(delay_seconds)

    try:
        if temporary.exists():
            temporary.unlink()
    except OSError:
        pass

    raise RuntimeError(
        "Не удалось заменить установленный RestaurantOSAgent.exe.\n\n"
        "Старый процесс или антивирус продолжает удерживать файл.\n"
        "Закройте панель агента и повторите установку.\n\n"
        f"Техническая ошибка: {last_error}"
    )


def install_files() -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    grant_data_permissions()

    configure_environment()
    write_default_env()

    current_exe = Path(sys.executable).resolve()
    installed_resolved = INSTALLED_EXE.resolve()

    # Критически важно: старая служба должна быть остановлена до
    # замены файла, иначе Windows возвращает WinError 32.
    remove_service(SERVICE_NAME)

    if current_exe != installed_resolved:
        replace_installed_executable(
            current_exe,
            INSTALLED_EXE,
        )

    run_hidden(
        ["attrib", "+h", str(DATA_DIR)],
        check=False,
    )
    grant_data_permissions()

    install_service(
        service_name=SERVICE_NAME,
        display_name=SERVICE_DISPLAY_NAME,
        description=(
            "Безопасное исходящее WebSocket-подключение "
            "TillyPad к Restaurant OS."
        ),
        executable_path=INSTALLED_EXE,
    )


def uninstall_agent() -> None:
    if not is_admin():
        relaunch_as_admin(["--uninstall"])
        return
    try:
        remove_service(SERVICE_NAME)

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

            self.stage(35, "Остановка старой службы и обновление приложения...")
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

            if key == "TILLYPAD_SQL_DRIVER":
                widget = ttk.Combobox(
                    settings,
                    textvariable=var,
                    values=installed_odbc_drivers(),
                    width=66,
                )
            else:
                widget = ttk.Entry(
                    settings,
                    textvariable=var,
                    show=show,
                    width=68,
                )

            widget.grid(
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

        ttk.Button(
            controls,
            text="Найти TillyPad автоматически",
            command=self.autodetect_tillypad,
        ).pack(side="left", padx=8)

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

        ttk.Button(
            diag_controls,
            text="Диагностика оплат",
            command=self.run_payment_schema_probe,
        ).pack(side="left", padx=8)

        ttk.Button(
            diag_controls,
            text="Сохранить оплаты JSON",
            command=self.export_payment_schema,
        ).pack(side="left")

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
        try:
            reload_marker = DATA_DIR / "reload_config.request"
            reload_marker.write_text("1", encoding="utf-8")
        except OSError:
            pass
        self.status.set(
            "Настройки сохранены. Служба перечитает их автоматически."
        )

        if show_message:
            messagebox.showinfo(
                APP_NAME,
                "Настройки сохранены.",
            )

    def generate_key(self):
        self.variables[
            "TILLYPAD_WS_API_KEY"
        ].set(secrets.token_urlsafe(48))

    def autodetect_tillypad(self):
        user = self.variables[
            "TILLYPAD_SQL_USER"
        ].get().strip()
        password = self.variables[
            "TILLYPAD_SQL_PASSWORD"
        ].get()

        if not user or not password:
            messagebox.showwarning(
                APP_NAME,
                (
                    "Сначала укажите SQL-логин и пароль.\n\n"
                    "Автопоиск не может подключаться к SQL "
                    "без учётных данных."
                ),
            )
            return

        self.status.set(
            "Идёт поиск локального SQL Server и базы TillyPad..."
        )
        threading.Thread(
            target=self._autodetect_worker,
            args=(user, password),
            daemon=True,
        ).start()

    def _autodetect_worker(self, user: str, password: str):
        def progress(message: str):
            self.after(
                0,
                lambda value=message: self.status.set(value),
            )

        try:
            results = find_tillypad(
                user=user,
                password=password,
                progress=progress,
            )
        except Exception as exc:
            self.after(
                0,
                lambda: messagebox.showerror(
                    APP_NAME,
                    f"Автопоиск не выполнен:\n{exc}",
                ),
            )
            return

        self.after(
            0,
            lambda: self._apply_autodetect_results(results),
        )

    def _apply_autodetect_results(self, results):
        if not results:
            self.status.set("База TillyPad не найдена")
            messagebox.showwarning(
                APP_NAME,
                (
                    "Не удалось автоматически найти базу TillyPad.\n\n"
                    "Проверьте SQL-логин, пароль, состояние службы "
                    "SQL Server и доступность TCP/IP."
                ),
            )
            return

        best = results[0]
        self.variables["TILLYPAD_SQL_SERVER"].set(
            best.server
        )
        self.variables["TILLYPAD_SQL_PORT"].set(
            best.port
        )
        self.variables["TILLYPAD_SQL_DATABASE"].set(
            best.database
        )
        self.variables["TILLYPAD_SQL_DRIVER"].set(
            best.driver
        )

        self.status.set(
            f"Найдена база {best.database} на {best.server}"
        )
        messagebox.showinfo(
            APP_NAME,
            (
                "TillyPad найден автоматически.\n\n"
                f"Сервер: {best.server}\n"
                f"База: {best.database}\n"
                f"Драйвер: {best.driver}\n\n"
                f"{best.details}"
            ),
        )

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

    def run_payment_schema_probe(self):
        self.save(show_message=False)
        self.status.set(
            "Читаю справочник и реальные строки оплат TillyPad..."
        )
        threading.Thread(
            target=self._payment_schema_worker,
            daemon=True,
        ).start()

    def _payment_schema_worker(self):
        try:
            report = discover_payment_schema(
                self.collect()
            )
            self.payment_schema_report = report
            self.after(
                0,
                lambda: self.show_payment_schema(report),
            )
        except Exception as exc:
            self.payment_schema_report = None
            self.after(
                0,
                lambda: messagebox.showerror(
                    APP_NAME,
                    "Не удалось исследовать таблицы оплат:\n"
                    + str(exc),
                ),
            )
            self.after(
                0,
                lambda: self.status.set(
                    "Поиск таблиц оплат завершился ошибкой"
                ),
            )

    def show_payment_schema(self, report):
        for item in self.tree.get_children():
            self.tree.delete(item)

        tables = report.get("candidate_tables") or []
        relationships = report.get("relationships") or []

        if not tables:
            self.tree.insert(
                "",
                "end",
                values=(
                    "Инфо",
                    "Совпадений по названиям таблиц/полей оплат не найдено",
                    "—",
                ),
            )
        else:
            for table in tables[:80]:
                keywords = ", ".join(
                    table.get("matched_keywords") or []
                )
                columns = ", ".join(
                    column.get("name", "")
                    for column in (
                        table.get("columns") or []
                    )[:12]
                )
                if len(table.get("columns") or []) > 12:
                    columns += ", …"

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        "Найдено",
                        (
                            f"{table.get('schema')}."
                            f"{table.get('table')} | "
                            f"ключи: {keywords} | "
                            f"поля: {columns}"
                        ),
                        "—",
                    ),
                )

        self.status.set(
            "Поиск оплат: "
            f"{len(tables)} таблиц-кандидатов, "
            f"{len(relationships)} связей. "
            "В JSON также добавлены PayTypes, CheckPayments и Checks. Сохраните и пришлите его."
        )

    def export_payment_schema(self):
        if not self.payment_schema_report:
            messagebox.showwarning(
                APP_NAME,
                (
                    "Сначала нажмите "
                    "«Найти таблицы оплат»."
                ),
            )
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="tillypad_payment_schema.json",
            filetypes=[("JSON", "*.json")],
        )
        if not filename:
            return

        save_payment_schema_report(
            self.payment_schema_report,
            Path(filename),
        )
        messagebox.showinfo(
            APP_NAME,
            (
                "Отчёт по структуре оплат сохранён.\n\n"
                "Пришлите этот JSON в чат."
            ),
        )

    def refresh_service(self):
        try:
            state = query_service(SERVICE_NAME)
            self.service_status.set(state.label)
        except Exception as exc:
            self.service_status.set(f"Ошибка службы: {exc}")

    def service_action(self, action: str):
        try:
            if action == "start":
                start_service(SERVICE_NAME)
            elif action == "stop":
                stop_service(SERVICE_NAME)
            elif action == "restart":
                restart_service(SERVICE_NAME)
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                f"Операция со службой не выполнена:\n{exc}",
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
