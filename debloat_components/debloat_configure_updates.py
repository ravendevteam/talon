import ctypes
import re
import sys
import time
import winreg
from contextlib import ExitStack
from ctypes import wintypes

from configuration_components.localization import t
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger
from utilities.util_modify_registry import set_value
from utilities.util_windows_check import supports_group_policy


_POLICY_PATH = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
_UPDATE_SETTINGS = {
    "DeferFeatureUpdates": 1,
    "DeferFeatureUpdatesPeriodInDays": 365,
    "DeferQualityUpdates": 1,
    "DeferQualityUpdatesPeriodInDays": 4,
    "ExcludeWUDriversInQualityUpdate": 1,
}
_AU_PATH = _POLICY_PATH + r"\AU"
_LEGACY_VERSION_PIN = {
    "ProductVersion": "Windows 11",
    "TargetReleaseVersion": 1,
    "TargetReleaseVersionInfo": "24H2",
}
_LEGACY_EXCLUSIONS = ";".join((
    "{e6cf1350-c01b-414d-a61f-263d3d4dd9f9}",
    "{b54e7d24-7add-49f4-88bb-9837d47477fb}",
    "{68c5b0a3-d1a6-4553-ae49-01d3a7827828}",
    "{b4832bd8-e735-4766-9727-7d0ffa644277}",
    "{28bc8804-5382-4bae-93aa-13c905f28542}",
    "{cd5ffd1e-e257-4a05-9d88-c83a7125d4c9}",
    "{0f1afbec-90ef-4651-9e37-030fedc944c8}",
    "{ebfc1fc5-71a4-4f7b-9aca-3b9a503104a0}",
    "{9920c092-3d99-4a1b-865a-673135c5a4fc}",
))
_SERVICE_STOPPED = 1
_SERVICE_RUNNING = 4
_SERVICE_PAUSED = 7
_SERVICE_QUERY_STATUS = 0x0004
_SERVICE_ENUMERATE_DEPENDENTS = 0x0008
_SERVICE_START = 0x0010
_SERVICE_STOP = 0x0020
_SERVICE_TIMEOUT = 60


class _ServiceStatus(ctypes.Structure):
    _fields_ = [(name, wintypes.DWORD) for name in (
        "service_type", "state", "controls_accepted", "win32_exit_code",
        "service_exit_code", "checkpoint", "wait_hint",
    )]


class _ServiceStatusProcess(ctypes.Structure):
    _fields_ = _ServiceStatus._fields_ + [
        ("process_id", wintypes.DWORD), ("service_flags", wintypes.DWORD),
    ]


class _ServiceEntry(ctypes.Structure):
    _fields_ = [
        ("name", wintypes.LPWSTR), ("display_name", wintypes.LPWSTR),
        ("status", _ServiceStatus),
    ]


def _service_api():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    signatures = {
        "OpenSCManagerW": (wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]),
        "OpenServiceW": (wintypes.HANDLE, [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]),
        "CloseServiceHandle": (wintypes.BOOL, [wintypes.HANDLE]),
        "QueryServiceStatusEx": (wintypes.BOOL, [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]),
        "ControlService": (wintypes.BOOL, [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(_ServiceStatus),
        ]),
        "StartServiceW": (wintypes.BOOL, [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.LPCWSTR),
        ]),
        "EnumDependentServicesW": (wintypes.BOOL, [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ]),
    }
    for name, (result_type, argument_types) in signatures.items():
        function = getattr(api, name)
        function.restype = result_type
        function.argtypes = argument_types
    return api


def _check_service_result(result, operation, accepted_errors=()):
    if not result:
        code = ctypes.get_last_error()
        if code not in accepted_errors:
            raise ctypes.WinError(code, f"{operation}: {ctypes.FormatError(code).strip()}")
        logger.debug("%s returned expected Windows error %s", operation, code)
    return result


def _wait_for_service(api, handle, name, states):
    deadline = time.monotonic() + _SERVICE_TIMEOUT
    previous_state = None
    while True:
        status = _ServiceStatusProcess()
        needed = wintypes.DWORD()
        _check_service_result(api.QueryServiceStatusEx(
            handle, 0, ctypes.byref(status), ctypes.sizeof(status), ctypes.byref(needed),
        ), f"QueryServiceStatusEx({name})")
        if status.state != previous_state:
            logger.debug("Service %s state: %s", name, status.state)
            previous_state = status.state
        if status.state in states:
            return status
        details = (f"state={status.state}, Windows exit={status.win32_exit_code}, "
                   f"service exit={status.service_exit_code}")
        if status.state == _SERVICE_STOPPED:
            raise RuntimeError(f"Service {name} stopped before reaching the requested state ({details}).")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Service {name} did not reach state {sorted(states)} "
                               f"within {_SERVICE_TIMEOUT} seconds ({details}).")
        time.sleep(min(1.0, max(0.1, status.wait_hint / 10000)))


def _dependent_services(api, handle, name):
    needed, count = wintypes.DWORD(), wintypes.DWORD()
    if api.EnumDependentServicesW(handle, 1, None, 0, ctypes.byref(needed), ctypes.byref(count)):
        return []
    _check_service_result(False, f"EnumDependentServicesW({name})", accepted_errors=(234,))
    buffer = ctypes.create_string_buffer(needed.value)
    _check_service_result(api.EnumDependentServicesW(
        handle, 1, buffer, len(buffer), ctypes.byref(needed), ctypes.byref(count),
    ), f"EnumDependentServicesW({name})")
    entries = ctypes.cast(buffer, ctypes.POINTER(_ServiceEntry))
    return [entries[index].name for index in range(count.value)]


def _restart_windows_update():
    api = _service_api()
    with ExitStack() as handles:
        def keep_handle(handle, operation):
            _check_service_result(handle, operation)
            def close():
                _check_service_result(api.CloseServiceHandle(handle), f"CloseServiceHandle({operation})")
            handles.callback(close)
            return handle

        manager = keep_handle(api.OpenSCManagerW(None, None, 0x0001), "OpenSCManagerW")
        stopped = []
        opened = {}

        def stop(name, restart=False):
            if name in opened:
                return
            access = _SERVICE_QUERY_STATUS | _SERVICE_ENUMERATE_DEPENDENTS | _SERVICE_START | _SERVICE_STOP
            handle = keep_handle(api.OpenServiceW(manager, name, access), f"OpenServiceW({name})")
            opened[name] = handle
            status = _wait_for_service(api, handle, name, {
                _SERVICE_STOPPED, _SERVICE_RUNNING, _SERVICE_PAUSED,
            })
            if status.state == _SERVICE_STOPPED:
                if restart:
                    stopped.append((name, handle))
                return
            for dependent in _dependent_services(api, handle, name):
                stop(dependent)
            logger.info("Stopping Windows service: %s", name)
            result = _ServiceStatus()
            _check_service_result(api.ControlService(handle, 1, ctypes.byref(result)),
                                  f"ControlService({name}, STOP)", accepted_errors=(1062,))
            if restart or status.state == _SERVICE_RUNNING:
                stopped.append((name, handle))
            _wait_for_service(api, handle, name, {_SERVICE_STOPPED})

        try:
            stop("wuauserv", restart=True)
        finally:
            restart_error = None
            for name, handle in reversed(stopped):
                try:
                    _wait_for_service(api, handle, name, {_SERVICE_STOPPED, _SERVICE_RUNNING})
                    logger.info("Starting Windows service: %s", name)
                    _check_service_result(api.StartServiceW(handle, 0, None),
                                          f"StartServiceW({name})", accepted_errors=(1056,))
                    _wait_for_service(api, handle, name, {_SERVICE_RUNNING})
                    logger.info("Windows service is running: %s", name)
                except Exception as error:
                    logger.exception("Failed to restart Windows service: %s", name)
                    if restart_error is None:
                        restart_error = error
            if restart_error is not None:
                raise restart_error


def _remove_legacy_policy(supported: bool) -> bool:
    access = winreg.KEY_READ | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _POLICY_PATH, 0, access)
    except FileNotFoundError:
        return False
    with key:
        def matches(name, value):
            try:
                actual, kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return False
            expected_kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            return actual == value and kind == expected_kind

        obsolete = []
        if supported and all(matches(name, value) for name, value in _LEGACY_VERSION_PIN.items()):
            obsolete.extend(_LEGACY_VERSION_PIN)
        if matches("ExcludeUpdateClassifications", _LEGACY_EXCLUSIONS):
            obsolete.append("ExcludeUpdateClassifications")
            if not supported and matches("ExcludeWUDriversInQualityUpdate", 1):
                obsolete.append("ExcludeWUDriversInQualityUpdate")
        if matches("AUOptions", 2):
            obsolete.append("AUOptions")
        for name in obsolete:
            winreg.DeleteValue(key, name)
            logger.info("Removed legacy Talon update policy: %s\\%s", _POLICY_PATH, name)
        return bool(obsolete)


def _home_update_settings():
    access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", 0, access) as key:
        release, kind = winreg.QueryValueEx(key, "DisplayVersion")
    if kind != winreg.REG_SZ or not isinstance(release, str) or not re.fullmatch(r"\d{2}H[12]", release):
        raise ValueError(f"Unable to determine the installed Windows release: {release!r}")
    return {
        "DeferQualityUpdates": 1,
        "DeferQualityUpdatesPeriodInDays": 4,
        "ProductVersion": "Windows 11",
        "TargetReleaseVersion": 1,
        "TargetReleaseVersionInfo": release,
    }


def main():
    try:
        supported = supports_group_policy(strict=True)
        settings = _UPDATE_SETTINGS if supported else _home_update_settings()
    except Exception as error:
        logger.exception("Failed to read Windows edition; update policies were left unchanged")
        show_error_popup(t("errors.windows_edition_failed", {"error": error}), allow_continue=False)
        sys.exit(1)
    try:
        _remove_legacy_policy(supported)
        if supported:
            logger.info("Applying Windows Update for Business deferral and download notification policies")
        else:
            logger.info("Applying Home registry update settings targeting Windows 11 %s",
                        settings["TargetReleaseVersionInfo"])
        for name, value in settings.items():
            kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            set_value(winreg.HKEY_LOCAL_MACHINE, _POLICY_PATH, name, value, kind)
        if supported:
            set_value(winreg.HKEY_LOCAL_MACHINE, _AU_PATH, "AUOptions", 2, winreg.REG_DWORD)
            _restart_windows_update()
    except Exception as error:
        logger.exception("Failed to configure Windows Update policy; some policy changes may already be in effect")
        show_error_popup(t("errors.update_policy_failed", {"error": error}), allow_continue=True)
        return
    logger.info("Windows update policy configured successfully.")


if __name__ == "__main__":
    main()
