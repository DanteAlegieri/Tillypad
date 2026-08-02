from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pywintypes
import win32con
import win32service


ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_NOT_ACTIVE = 1062
ERROR_INVALID_SERVICE_CONTROL = 1052


@dataclass
class ServiceState:
    exists: bool
    status: int | None
    label: str


def _open_manager(access: int):
    return win32service.OpenSCManager(None, None, access)


def query_service(service_name: str) -> ServiceState:
    manager = _open_manager(win32service.SC_MANAGER_CONNECT)
    try:
        try:
            service = win32service.OpenService(
                manager,
                service_name,
                win32service.SERVICE_QUERY_STATUS,
            )
        except pywintypes.error as exc:
            if exc.winerror == ERROR_SERVICE_DOES_NOT_EXIST:
                return ServiceState(False, None, "Служба не установлена")
            raise
        try:
            status = win32service.QueryServiceStatus(service)[1]
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)

    labels = {
        win32service.SERVICE_STOPPED: "Служба остановлена",
        win32service.SERVICE_START_PENDING: "Служба запускается",
        win32service.SERVICE_STOP_PENDING: "Служба останавливается",
        win32service.SERVICE_RUNNING: "Служба запущена",
        win32service.SERVICE_CONTINUE_PENDING: "Служба продолжает работу",
        win32service.SERVICE_PAUSE_PENDING: "Служба приостанавливается",
        win32service.SERVICE_PAUSED: "Служба приостановлена",
    }
    return ServiceState(True, status, labels.get(status, f"Состояние службы: {status}"))


def _wait(service, expected: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if win32service.QueryServiceStatus(service)[1] == expected:
            return True
        time.sleep(0.4)
    return False


def stop_service(service_name: str) -> None:
    manager = _open_manager(win32service.SC_MANAGER_CONNECT)
    try:
        try:
            service = win32service.OpenService(
                manager,
                service_name,
                win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS,
            )
        except pywintypes.error as exc:
            if exc.winerror == ERROR_SERVICE_DOES_NOT_EXIST:
                return
            raise
        try:
            if win32service.QueryServiceStatus(service)[1] == win32service.SERVICE_STOPPED:
                return
            try:
                win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
            except pywintypes.error as exc:
                if exc.winerror not in (ERROR_SERVICE_NOT_ACTIVE, ERROR_INVALID_SERVICE_CONTROL):
                    raise
            _wait(service, win32service.SERVICE_STOPPED)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)


def start_service(service_name: str) -> None:
    manager = _open_manager(win32service.SC_MANAGER_CONNECT)
    try:
        service = win32service.OpenService(
            manager,
            service_name,
            win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS,
        )
        try:
            if win32service.QueryServiceStatus(service)[1] != win32service.SERVICE_RUNNING:
                win32service.StartService(service, None)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)


def restart_service(service_name: str) -> None:
    stop_service(service_name)
    start_service(service_name)


def remove_service(service_name: str) -> None:
    stop_service(service_name)

    manager = _open_manager(win32service.SC_MANAGER_CONNECT)
    try:
        try:
            service = win32service.OpenService(
                manager,
                service_name,
                win32con.DELETE,
            )
        except pywintypes.error as exc:
            if exc.winerror == ERROR_SERVICE_DOES_NOT_EXIST:
                return
            raise
        try:
            win32service.DeleteService(service)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)

    time.sleep(1.5)


def install_service(
    *,
    service_name: str,
    display_name: str,
    description: str,
    executable_path: Path,
) -> None:
    remove_service(service_name)

    manager = _open_manager(win32service.SC_MANAGER_CREATE_SERVICE)
    service = None
    try:
        binary_path = f'"{executable_path}" --run-service'
        service = win32service.CreateService(
            manager,
            service_name,
            display_name,
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
            description,
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
            win32service.ChangeServiceConfig2(
                service,
                win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG,
                True,
            )
        except (AttributeError, pywintypes.error):
            pass
        win32service.StartService(service, None)
    finally:
        if service is not None:
            win32service.CloseServiceHandle(service)
        win32service.CloseServiceHandle(manager)
