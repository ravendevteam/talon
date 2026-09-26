import ctypes
import os
import subprocess
import uuid
import winreg
from contextlib import ExitStack

from configuration_components.localization import t
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger
from utilities.util_process import run_logged_process
from utilities.util_windows_check import supports_group_policy


_POLICY_ROOTS = (r"software\policies", r"software\microsoft\windows\currentversion\policies")
_FIELDS = {"hive", "key_path", "name", "value_type", "value"}


def normalize_group_policy_changes(value):
    if not isinstance(value, list):
        raise ValueError("Group Policy changes must be a JSON array.")
    normalized, targets = [], set()
    for index, row in enumerate(value):
        label = f"Group Policy change {index + 1}"
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError(f"{label} must contain exactly hive, key_path, name, value_type, and value.")
        if any(not isinstance(row[field], str) for field in _FIELDS - {"value"}):
            raise ValueError(f"{label}: hive, key_path, name, and value_type must be strings.")
        hive = {"HKLM": "HKLM", "HKEY_LOCAL_MACHINE": "HKLM",
                "HKCU": "HKCU", "HKEY_CURRENT_USER": "HKCU"}.get(row["hive"].strip().upper())
        path, name = row["key_path"].strip(), row["name"].strip()
        value_type, data = row["value_type"].strip().upper(), row["value"]
        if hive is None:
            raise ValueError(f"{label}: hive must be HKLM or HKCU.")
        if (not path or len(path) > 255 or any(ord(c) < 32 for c in path)
                or "/" in path or any(part in ("", ".", "..") for part in path.split("\\"))
                or not any(path.casefold() == root or path.casefold().startswith(root + "\\")
                           for root in _POLICY_ROOTS)):
            raise ValueError(f"{label}: key_path must be within Software\\Policies or "
                             "Software\\Microsoft\\Windows\\CurrentVersion\\Policies.")
        if not name or len(name) > 16383 or name.startswith("**") or any(ord(c) < 32 for c in name):
            raise ValueError(f"{label}: name must be a nonempty registry value name without ** directives.")
        if value_type == "REG_DWORD":
            if type(data) is not int or not 0 <= data <= 0xFFFFFFFF:
                raise ValueError(f"{label}: REG_DWORD value must be an integer from 0 to 4294967295.")
        elif value_type == "REG_SZ":
            if not isinstance(data, str) or "\0" in data:
                raise ValueError(f"{label}: REG_SZ value must be a string without null characters.")
        else:
            raise ValueError(f"{label}: value_type must be REG_DWORD or REG_SZ.")
        target = (hive, path.casefold(), name.casefold())
        if target in targets:
            raise ValueError(f"{label}: duplicate policy target.")
        targets.add(target)
        normalized.append(dict(hive=hive, key_path=path, name=name, value_type=value_type, value=data))
    return normalized


class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check_hresult(result, operation):
    if result < 0:
        raise OSError(f"{operation} failed (HRESULT 0x{result & 0xFFFFFFFF:08X}).")


class _LocalGroupPolicy:

    def __init__(self):
        self._pointer = ctypes.c_void_p()
        self._initialized = False

    def _method(self, index, result_type, *argument_types):
        table = ctypes.cast(self._pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[index])

    def __enter__(self):
        self._ole32 = ctypes.WinDLL("ole32")
        self._ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._ole32.CoInitializeEx.restype = ctypes.c_int32
        self._ole32.CoUninitialize.argtypes = []
        self._ole32.CoUninitialize.restype = None
        self._ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p,
                                                ctypes.c_uint32, ctypes.POINTER(_GUID),
                                                ctypes.POINTER(ctypes.c_void_p)]
        self._ole32.CoCreateInstance.restype = ctypes.c_int32
        _check_hresult(self._ole32.CoInitializeEx(None, 2), "CoInitializeEx")
        self._initialized = True
        try:
            clsid = _GUID.parse("EA502722-A23D-11D1-A7D3-0000F87571E3")
            iid = _GUID.parse("EA502723-A23D-11D1-A7D3-0000F87571E3")
            _check_hresult(self._ole32.CoCreateInstance(ctypes.byref(clsid), None, 1,
                           ctypes.byref(iid), ctypes.byref(self._pointer)), "CoCreateInstance")
            if not self._pointer:
                raise OSError("The Local Group Policy API returned no interface.")
            _check_hresult(self._method(5, ctypes.c_int32, ctypes.c_uint32)(self._pointer, 1),
                           "OpenLocalMachineGPO")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def registry_root(self, hive):
        handle = ctypes.c_void_p()
        _check_hresult(self._method(15, ctypes.c_int32, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_void_p))(self._pointer, 2 if hive == "HKLM" else 1,
                                                       ctypes.byref(handle)), "GetRegistryKey")
        if not handle.value:
            raise OSError("The Local Group Policy API returned no registry handle.")
        return handle.value

    def save(self, hive):
        extension = _GUID.parse("35378EAC-683F-11D2-A89A-00C04FBBCFA2")
        editor = _GUID.parse("8FC0B734-A0E1-11D1-A7D3-0000F87571E3")
        _check_hresult(self._method(7, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                       ctypes.POINTER(_GUID), ctypes.POINTER(_GUID))(
                           self._pointer, int(hive == "HKLM"), 1, ctypes.byref(extension),
                           ctypes.byref(editor)), f"Save({hive})")

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._pointer:
                self._method(2, ctypes.c_uint32)(self._pointer)
                self._pointer = ctypes.c_void_p()
        finally:
            if self._initialized:
                self._ole32.CoUninitialize()
                self._initialized = False


def _apply_group_policy(changes):
    hives = list(dict.fromkeys(row["hive"] for row in changes))
    with _LocalGroupPolicy() as policy:
        with ExitStack() as handles:
            roots = {}
            for hive in hives:
                roots[hive] = policy.registry_root(hive)
                handles.callback(winreg.CloseKey, roots[hive])
            for row in changes:
                with winreg.CreateKeyEx(roots[row["hive"]], row["key_path"], 0, winreg.KEY_SET_VALUE) as key:
                    kind = winreg.REG_DWORD if row["value_type"] == "REG_DWORD" else winreg.REG_SZ
                    winreg.SetValueEx(key, row["name"], 0, kind, row["value"])
        for hive in hives:
            policy.save(hive)
            logger.info(f"Saved Local Group Policy section {hive}.")
    for hive in hives:
        target = "computer" if hive == "HKLM" else "user"
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        system_dir = "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"
        result = run_logged_process(
            [os.path.join(system_root, system_dir, "gpupdate.exe"), f"/target:{target}",
             "/force", "/wait:120"],
            label=f"gpupdate ({target})", timeout=150, encoding=None,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Policy was saved, but gpupdate for {target} failed "
                               f"(exit code {result.returncode}).")


def _fail(message):
    logger.error(message)
    show_error_popup(message, allow_continue=False)
    raise SystemExit(1)


def main(group_policy_changes=None):
    if not supports_group_policy():
        _fail(t("errors.group_policy_unsupported"))
    try:
        changes = normalize_group_policy_changes(group_policy_changes)
    except ValueError as error:
        _fail(t("errors.group_policy_invalid", {"error": error}))
    if not changes:
        _fail(t("errors.group_policy_empty"))
    try:
        _apply_group_policy(changes)
    except Exception as error:
        logger.exception("Local Group Policy changes failed; any sections already saved remain in effect.")
        show_error_popup(t("errors.group_policy_failed", {"error": error}), allow_continue=True)
        return
    logger.info(f"Applied and refreshed {len(changes)} Local Group Policy changes.")


if __name__ == "__main__":
    main()
