from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Restaurant OS Relay Agent"
SERVICE_NAME = "GastrodomRelayAgent"
INSTALL_DIR = Path(
    os.environ.get("ProgramFiles", r"C:\Program Files")
) / "Gastrodom" / "RelayAgent"
DATA_DIR = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
) / "Gastrodom" / "RelayAgent"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )
    if result <= 32:
        raise RuntimeError(
            "Не удалось запросить права администратора."
        )


def bundled_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / name


def run_hidden(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
        creationflags=creationflags,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            (result.stdout + "\n" + result.stderr).strip()
            or f"Команда завершилась с кодом {result.returncode}"
        )
    return result


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("700x480")
        self.resizable(False, False)

        self.status = tk.StringVar(value="Готово к установке")
        self.progress = tk.DoubleVar(value=0)

        self._build()

    def _build(self):
        root = ttk.Frame(self, padding=28)
        root.pack(fill="both", expand=True)

        ttk.Label(
            root,
            text="Restaurant OS Relay Agent",
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            root,
            text=(
                "Подключение TillyPad к Restaurant OS "
                "через безопасный WebSocket Gateway"
            ),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(6, 22))

        card = ttk.LabelFrame(
            root,
            text="Что будет установлено",
            padding=18,
        )
        card.pack(fill="x")

        items = [
            "Служба Windows без консольного окна",
            "Автоматический запуск вместе с Windows",
            "Панель настройки и диагностики",
            "Защищённая конфигурация в ProgramData",
            "Автоматическое переподключение к Gateway",
        ]
        for item in items:
            ttk.Label(
                card,
                text=f"✓  {item}",
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=3)

        ttk.Progressbar(
            root,
            variable=self.progress,
            maximum=100,
        ).pack(fill="x", pady=(24, 8))

        ttk.Label(
            root,
            textvariable=self.status,
        ).pack(anchor="w")

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", pady=(24, 0))

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

    def set_stage(self, value: int, text: str):
        self.progress.set(value)
        self.status.set(text)
        self.update_idletasks()

    def install(self):
        self.install_button.configure(state="disabled")
        try:
            self.set_stage(5, "Проверка прав администратора...")
            if not is_admin():
                relaunch_as_admin()
                self.destroy()
                return

            self.set_stage(15, "Подготовка каталогов...")
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / "logs").mkdir(exist_ok=True)
            (DATA_DIR / "cache").mkdir(exist_ok=True)

            self.set_stage(30, "Копирование программы...")
            service_src = bundled_path("AgentService.exe")
            manager_src = bundled_path("AgentManager.exe")
            env_src = bundled_path("agent.env.example")

            if not service_src.exists():
                raise FileNotFoundError(service_src)
            if not manager_src.exists():
                raise FileNotFoundError(manager_src)

            service_dst = INSTALL_DIR / "AgentService.exe"
            manager_dst = INSTALL_DIR / "AgentManager.exe"

            shutil.copy2(service_src, service_dst)
            shutil.copy2(manager_src, manager_dst)

            env_dst = DATA_DIR / "agent.env"
            if not env_dst.exists() and env_src.exists():
                shutil.copy2(env_src, env_dst)

            self.set_stage(45, "Защита конфигурации...")
            run_hidden(["attrib", "+h", str(DATA_DIR)], check=False)
            run_hidden(
                [
                    "icacls",
                    str(DATA_DIR),
                    "/inheritance:r",
                ],
                check=False,
            )
            run_hidden(
                [
                    "icacls",
                    str(DATA_DIR),
                    "/grant:r",
                    "SYSTEM:(OI)(CI)F",
                    "Administrators:(OI)(CI)F",
                ],
                check=False,
            )

            self.set_stage(60, "Обновление службы...")
            run_hidden(
                ["sc.exe", "stop", SERVICE_NAME],
                check=False,
            )
            run_hidden(
                ["sc.exe", "delete", SERVICE_NAME],
                check=False,
            )

            self.set_stage(72, "Регистрация службы Windows...")
            bin_path = f'"{service_dst}"'
            run_hidden(
                [
                    "sc.exe",
                    "create",
                    SERVICE_NAME,
                    f"binPath= {bin_path}",
                    "start= auto",
                    "DisplayName= Restaurant OS Relay Agent",
                ]
            )
            run_hidden(
                [
                    "sc.exe",
                    "description",
                    SERVICE_NAME,
                    (
                        "Безопасное исходящее WebSocket-подключение "
                        "TillyPad к Restaurant OS."
                    ),
                ],
                check=False,
            )

            self.set_stage(82, "Настройка восстановления после сбоя...")
            run_hidden(
                [
                    "sc.exe",
                    "failure",
                    SERVICE_NAME,
                    "reset= 86400",
                    "actions= restart/5000/restart/15000/restart/60000",
                ],
                check=False,
            )
            run_hidden(
                ["sc.exe", "failureflag", SERVICE_NAME, "1"],
                check=False,
            )

            self.set_stage(90, "Запуск службы...")
            run_hidden(
                ["sc.exe", "start", SERVICE_NAME],
                check=False,
            )

            self.set_stage(100, "Установка завершена")
            messagebox.showinfo(
                APP_NAME,
                (
                    "Агент успешно установлен.\n\n"
                    "Сейчас откроется панель настройки."
                ),
            )

            subprocess.Popen(
                [str(manager_dst)],
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


if __name__ == "__main__":
    Installer().mainloop()
