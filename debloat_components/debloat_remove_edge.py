import ctypes
import os
import re
import stat
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from configuration_components.localization import t
from utilities.util_admin_check import ensure_admin
from utilities.util_error_popup import show_error_popup
from utilities.util_file_cleanup import checked_cleanup_path, remove_path
from utilities.util_logger import logger
from utilities.util_process import run_logged_process
from utilities.util_shell import refresh_shell, remove_shortcuts, shortcut_roots, stop_processes


_EDGE_APP_ID = "{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}"
_EDGE_EXECUTABLES = ("msedge.exe", "msedge_proxy.exe", "msedge_pwa_launcher.exe")
_VERSION_DIRECTORY = re.compile(r"\d+\.\d+\.\d+\.\d+", re.ASCII)
_UPDATE_POLICY_PATH = r"SOFTWARE\Policies\Microsoft\EdgeUpdate"


def _installation_locations():
    locations = []
    seen = set()
    for variable, machine in (("ProgramFiles(x86)", True), ("ProgramW6432", True),
                              ("ProgramFiles", True), ("LOCALAPPDATA", False)):
        base = os.environ.get(variable)
        if not base:
            continue
        if not os.path.isabs(base):
            raise ValueError(f"Windows environment path {variable} is not absolute: {base}")
        parent = os.path.join(os.path.abspath(base), "Microsoft")
        application = os.path.join(parent, "Edge", "Application")
        normalized = os.path.normcase(application)
        if normalized not in seen:
            checked_cleanup_path(application, parent)
            locations.append((application, parent, machine))
            seen.add(normalized)
    if not locations:
        raise RuntimeError("No Windows application directories are available for Edge removal.")
    return locations


def _checked_installation_path(path, parent):
    path = checked_cleanup_path(path, parent)
    current = os.path.abspath(parent)
    for part in ("", *os.path.relpath(path, parent).split(os.sep)):
        current = os.path.join(current, part)
        try:
            attributes = os.lstat(current).st_file_attributes
        except FileNotFoundError:
            return path
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Refusing to modify a redirected Edge installation: {current}")
    return path


def _find_installer(application, parent):
    _checked_installation_path(application, parent)
    try:
        with os.scandir(application) as entries:
            versions = [entry.name for entry in entries
                        if _VERSION_DIRECTORY.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return None
    versions.sort(key=lambda value: tuple(int(part) for part in value.split(".")), reverse=True)
    for version in versions:
        installer = _checked_installation_path(os.path.join(application, version, "Installer", "setup.exe"), parent)
        try:
            details = os.stat(installer, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISREG(details.st_mode):
            return installer
    return None


def _uninstall(application, parent, machine):
    installer = _find_installer(application, parent)
    if installer is None:
        logger.info("No Edge uninstaller is present in %s; checking application-file cleanup", application)
        return
    command = [installer, "--uninstall", "--msedge", "--force-uninstall", "--verbose-logging"]
    if machine:
        command.append("--system-level")
    result = run_logged_process(command, label=f"Edge uninstaller ({application})", encoding=None, timeout=300)
    logger.info("Edge uninstaller returned %s for %s; application removal will be verified",
                result.returncode, application)
    if result.returncode not in (0, 19, 29, 3010):
        logger.warning("Edge uninstaller failed with exit code %s: %s; attempting application-file cleanup",
                       result.returncode, installer)
    if result.returncode in (29, 3010):
        logger.warning("Edge uninstaller requested a restart; checking whether application files remain")


def _remove_application(application, parent):
    _checked_installation_path(application, parent)
    remove_path(application, parent)


def _verify_removed(locations):
    remaining = []
    for application, parent, _ in locations:
        _checked_installation_path(application, parent)
        try:
            os.lstat(application)
        except FileNotFoundError:
            continue
        remaining.append(application)
    if remaining:
        raise RuntimeError("Edge application directories remain after removal: " + ", ".join(remaining))


def _delete_registry_tree(hive, path, view):
    parent, _, name = path.rpartition("\\")
    if not parent or not name:
        raise ValueError(f"Invalid Edge registry cleanup path: {path}")
    try:
        with winreg.OpenKey(hive, parent, 0, winreg.KEY_READ | winreg.KEY_WRITE | 0x00010000 | view) as key:
            api = ctypes.WinDLL("advapi32", use_last_error=True)
            api.RegDeleteTreeW.argtypes = [wintypes.HKEY, wintypes.LPCWSTR]
            api.RegDeleteTreeW.restype = wintypes.LONG
            result = api.RegDeleteTreeW(int(key), name)
            if result == 2:
                logger.debug("Edge registry entry is already absent: %s", path)
                return
            if result:
                raise ctypes.WinError(result)
        logger.info("Removed Edge registry entry: %s (view=%s)", path, view)
    except FileNotFoundError:
        logger.debug("Edge registry entry is already absent: %s", path)


def _validate_registered_locations(application_roots):
    allowed = {os.path.normcase(os.path.join(root, "msedge.exe")) for root in application_roots}
    path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "")
            except FileNotFoundError:
                continue
            if not isinstance(value, str):
                raise ValueError("Edge App Paths registration is not a string")
            target = os.path.normcase(os.path.abspath(os.path.expandvars(value.strip().strip('"'))))
            if target not in allowed:
                raise RuntimeError(f"Edge is registered outside the supported installation directories: {value}. "
                                   "Its files and updater registrations will be preserved.")


def _remove_registrations(application_roots):
    _validate_registered_locations(application_roots)
    failures = []
    allowed = {os.path.normcase(os.path.join(root, name))
               for root in application_roots for name in _EDGE_EXECUTABLES}
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                if not isinstance(value, str):
                    raise ValueError("Edge App Paths registration is not a string")
                target = os.path.normcase(os.path.abspath(os.path.expandvars(value.strip().strip('"'))))
                if target in allowed:
                    _delete_registry_tree(hive, path, view)
                else:
                    logger.info("Preserving App Paths registration outside the removed Edge installations: %s", value)
            except FileNotFoundError:
                logger.debug("Edge App Paths registration is already absent (hive=%s, view=%s)", hive, view)
            except Exception as error:
                logger.exception("Unable to clean Edge App Paths registration (hive=%s, view=%s)", hive, view)
                failures.append(f"Edge App Paths registration: {error}")
            for branch in ("Clients", "ClientState", "ClientStateMedium"):
                path = "SOFTWARE\\Microsoft\\EdgeUpdate\\" + branch + "\\" + _EDGE_APP_ID
                try:
                    _delete_registry_tree(hive, path, view)
                except Exception as error:
                    logger.exception("Unable to remove stable Edge updater registration: %s", path)
                    failures.append(f"{path}: {error}")
    return failures


def _is_domain_joined():
    api = ctypes.WinDLL("netapi32", use_last_error=True)
    api.NetGetJoinInformation.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                         ctypes.POINTER(wintypes.DWORD)]
    api.NetGetJoinInformation.restype = wintypes.DWORD
    api.NetApiBufferFree.argtypes = [ctypes.c_void_p]
    api.NetApiBufferFree.restype = wintypes.DWORD
    name, status = ctypes.c_void_p(), wintypes.DWORD()
    try:
        result = api.NetGetJoinInformation(None, ctypes.byref(name), ctypes.byref(status))
        if result:
            raise ctypes.WinError(result)
        return status.value == 3
    finally:
        if name:
            result = api.NetApiBufferFree(name)
            if result:
                raise ctypes.WinError(result)


def _limit_reinstallation():
    if not _is_domain_joined():
        logger.info("Edge installation policy requires an Active Directory domain; Windows may reinstall Edge")
        return
    name = "Install" + _EDGE_APP_ID
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, _UPDATE_POLICY_PATH, 0,
                           winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 0)
    logger.info("Disabled stable Edge installation through Edge Update policy; other installation methods may still restore Edge")


def _remove_edge():
    locations = _installation_locations()
    application_roots = [application for application, _, _ in locations]
    for application, parent, _ in locations:
        _checked_installation_path(application, parent)
    _validate_registered_locations(application_roots)
    failures = stop_processes(_EDGE_EXECUTABLES, allowed_executable_roots=application_roots,
                              graceful_timeout_ms=3000)
    if failures:
        raise RuntimeError("Unable to stop Edge safely:\n" + "\n".join(failures))

    def perform(label, action, *args, **kwargs):
        try:
            result = action(*args, **kwargs)
            if isinstance(result, list):
                failures.extend(result)
                return not result
            return True
        except Exception as error:
            logger.exception("%s failed", label)
            failures.append(f"{label}: {error}")
            return False

    for application, parent, machine in locations:
        perform(f"Uninstall Edge from {application}", _uninstall, application, parent, machine)
    stop_failures = stop_processes(_EDGE_EXECUTABLES, allowed_executable_roots=application_roots,
                                  graceful_timeout_ms=3000)
    failures.extend(stop_failures)
    if not stop_failures:
        for application, parent, _ in locations:
            perform(f"Remove Edge application files from {application}", _remove_application, application, parent)
    try:
        _verify_removed(locations)
        _validate_registered_locations(application_roots)
    except Exception as error:
        logger.exception("Edge removal verification failed")
        failures.append(str(error))
    else:
        if perform("Clean Edge registrations", _remove_registrations, application_roots):
            perform("Apply stable Edge installation policy", _limit_reinstallation)
        try:
            roots, root_failures = shortcut_roots()
            failures.extend(root_failures)
            perform("Remove Edge shortcuts", remove_shortcuts, roots,
                    allowed_executable_roots=application_roots, executable_names=_EDGE_EXECUTABLES)
        except Exception as error:
            logger.exception("Unable to discover Edge shortcut directories")
            failures.append(f"Edge shortcut directories: {error}")
    perform("Refresh the Windows shell", refresh_shell)
    if failures:
        raise RuntimeError("Some Edge removal operations failed:\n" + "\n".join(failures))


def main():
    ensure_admin()
    try:
        _remove_edge()
    except Exception as error:
        logger.exception("Microsoft Edge removal failed")
        show_error_popup(t("errors.edge_removal_failed", {"error": error}), allow_continue=True)
        logger.warning("Continuing after incomplete Microsoft Edge removal")
        return
    logger.info("Microsoft Edge removal completed; browser profiles and shared runtimes were preserved.")


if __name__ == "__main__":
    main()
