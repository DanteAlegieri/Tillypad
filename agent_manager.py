from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk, filedialog

from app.agent_diagnostics import (
    export_support_report,
    load_env_file,
    run_all,
)


APP_TITLE = "Restaurant OS Agent Manager"
DATA_DIR = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
) / "Gastrodom" / "RelayAgent"
ENV_FILE = DATA_DIR / "agent.env"
SERVICE_NAME = "GastrodomRelayAgent"


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


DEFAULTS = {
    "TILLYPAD_SQL_SERVER": "127.0.0.1",
    "TILLYPAD_SQL_PORT": "1433",
    "TILLYPAD_SQL_DATABASE": "TillypadSegment",
    "TILLYPAD_SQL_DRIVER": "ODBC Driver 18 for SQL Server",
    "TILLYPAD_AGENT_ID": os.environ.get("COMPUTERNAME", "gastrodom-main").lower(),
    "TILLYPAD_WS_GATEWAY_URL": "wss://gateway.example.ru/ws/agent",
    "TILLYPAD_WS_HEARTBEAT": "20",
    "TILLYPAD_WS_RECONNECT_MAX": "60",
    "TILLYPAD_SQL_ENCRYPT": "no",
    "TILLYPAD_SQL_TRUST_CERTIFICATE": "yes",
    "TILLYPAD_SQL_TIMEOUT": "10",
}


class AgentManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x670")
        self.minsize(820, 600)

        self.variables: dict[str, tk.StringVar] = {}
        self.status_var = tk.StringVar(value="Готово")
        self.service_var = tk.StringVar(value="Проверка...")
        self.results = []

        self._build_ui()
        self._load_settings()
        self._refresh_service_status()

    def _build_ui(self):
        header = ttk.Frame(self, padding=18)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Restaurant OS Relay Agent",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Настройка подключения TillyPad к WebSocket Gateway",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self, padding=(18, 0, 18, 18))
        body.pack(fill="both", expand=True)

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        settings_tab = ttk.Frame(notebook, padding=16)
        diagnostics_tab = ttk.Frame(notebook, padding=16)
        service_tab = ttk.Frame(notebook, padding=16)

        notebook.add(settings_tab, text="Настройки")
        notebook.add(diagnostics_tab, text="Диагностика")
        notebook.add(service_tab, text="Служба")

        # Settings
        for row, (key, label) in enumerate(FIELDS):
            ttk.Label(settings_tab, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=6
            )
            var = tk.StringVar()
            self.variables[key] = var
            show = "*" if "PASSWORD" in key or "API_KEY" in key else ""
            entry = ttk.Entry(settings_tab, textvariable=var, show=show, width=68)
            entry.grid(row=row, column=1, sticky="ew", pady=6)

        settings_tab.columnconfigure(1, weight=1)

        buttons = ttk.Frame(settings_tab)
        buttons.grid(
            row=len(FIELDS), column=0, columnspan=2,
            sticky="ew", pady=(16, 0)
        )
        ttk.Button(
            buttons, text="Сохранить", command=self._save_settings
        ).pack(side="left")
        ttk.Button(
            buttons, text="Сгенерировать API-ключ",
            command=self._generate_key
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons, text="Проверить всё",
            command=self._run_diagnostics
        ).pack(side="left")

        # Diagnostics
        self.diag_tree = ttk.Treeview(
            diagnostics_tab,
            columns=("status", "message", "time"),
            show="headings",
            height=12,
        )
        self.diag_tree.heading("status", text="Статус")
        self.diag_tree.heading("message", text="Результат")
        self.diag_tree.heading("time", text="Время")
        self.diag_tree.column("status", width=100, anchor="center")
        self.diag_tree.column("message", width=560)
        self.diag_tree.column("time", width=100, anchor="center")
        self.diag_tree.pack(fill="both", expand=True)

        diag_buttons = ttk.Frame(diagnostics_tab)
        diag_buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(
            diag_buttons,
            text="Запустить диагностику",
            command=self._run_diagnostics,
        ).pack(side="left")
        ttk.Button(
            diag_buttons,
            text="Отчёт для поддержки",
            command=self._export_report,
        ).pack(side="left", padx=8)

        # Service
        ttk.Label(
            service_tab,
            textvariable=self.service_var,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", pady=(0, 16))

        svc_buttons = ttk.Frame(service_tab)
        svc_buttons.pack(anchor="w")
        ttk.Button(
            svc_buttons, text="Запустить",
            command=lambda: self._service_action("start")
        ).pack(side="left")
        ttk.Button(
            svc_buttons, text="Остановить",
            command=lambda: self._service_action("stop")
        ).pack(side="left", padx=8)
        ttk.Button(
            svc_buttons, text="Перезапустить",
            command=lambda: self._service_action("restart")
        ).pack(side="left")
        ttk.Button(
            svc_buttons, text="Обновить статус",
            command=self._refresh_service_status
        ).pack(side="left", padx=8)

        ttk.Separator(service_tab).pack(fill="x", pady=20)
        ttk.Label(
            service_tab,
            text=(
                "Служба работает без окна и автоматически "
                "переподключается к Gateway."
            ),
            wraplength=700,
        ).pack(anchor="w")

        footer = ttk.Frame(self, padding=(18, 8))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(anchor="w")

    def _load_settings(self):
        settings = dict(DEFAULTS)
        settings.update(load_env_file(ENV_FILE))
        for key, _ in FIELDS:
            self.variables[key].set(settings.get(key, ""))

    def _collect_settings(self):
        settings = dict(DEFAULTS)
        for key, var in self.variables.items():
            settings[key] = var.get().strip()
        return settings

    def _save_settings(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            settings = self._collect_settings()
            lines = [
                "# Restaurant OS Relay Agent",
                "# Создано Agent Manager",
                "",
            ]
            lines.extend(f"{k}={v}" for k, v in settings.items())
            ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.status_var.set(f"Настройки сохранены: {ENV_FILE}")
            messagebox.showinfo(APP_TITLE, "Настройки сохранены.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def _generate_key(self):
        self.variables["TILLYPAD_WS_API_KEY"].set(
            secrets.token_urlsafe(48)
        )

    def _run_diagnostics(self):
        self._save_settings()
        self.status_var.set("Выполняется диагностика...")
        threading.Thread(
            target=self._diagnostics_worker,
            daemon=True,
        ).start()

    def _diagnostics_worker(self):
        settings = self._collect_settings()
        results = run_all(settings)
        self.results = results
        self.after(0, lambda: self._show_results(results))

    def _show_results(self, results):
        for item in self.diag_tree.get_children():
            self.diag_tree.delete(item)
        for result in results:
            self.diag_tree.insert(
                "",
                "end",
                values=(
                    "Успешно" if result.ok else "Ошибка",
                    f"{result.name}: {result.message}",
                    f"{result.duration_ms} мс",
                ),
            )
        ok_count = sum(1 for item in results if item.ok)
        self.status_var.set(
            f"Диагностика завершена: {ok_count}/{len(results)} успешно"
        )

    def _export_report(self):
        if not self.results:
            messagebox.showwarning(
                APP_TITLE,
                "Сначала запустите диагностику.",
            )
            return
        filename = filedialog.asksaveasfilename(
            title="Сохранить отчёт",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not filename:
            return
        export_support_report(
            self._collect_settings(),
            self.results,
            Path(filename),
        )
        messagebox.showinfo(APP_TITLE, "Отчёт сохранён.")

    def _run_sc(self, *args):
        return subprocess.run(
            ["sc.exe", *args],
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
        )

    def _refresh_service_status(self):
        result = self._run_sc("query", SERVICE_NAME)
        text = (result.stdout + result.stderr).upper()
        if "RUNNING" in text:
            status = "Служба запущена"
        elif "STOPPED" in text:
            status = "Служба остановлена"
        else:
            status = "Служба не установлена"
        self.service_var.set(status)

    def _service_action(self, action):
        try:
            if action == "restart":
                self._run_sc("stop", SERVICE_NAME)
                self.after(1200, lambda: self._service_action("start"))
                return
            command = "start" if action == "start" else "stop"
            result = self._run_sc(command, SERVICE_NAME)
            if result.returncode not in {0, 1062}:
                raise RuntimeError(result.stdout + result.stderr)
            self.after(1200, self._refresh_service_status)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))


if __name__ == "__main__":
    AgentManager().mainloop()
