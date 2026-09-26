import os
import stat
import sys
import winreg
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from configuration_components.localization import t
from utilities.util_admin_check import ensure_admin
from utilities.util_appx import remove_outlook_packages
from utilities.util_error_popup import show_error_popup
from utilities.util_file_cleanup import checked_cleanup_path, remove_path
from utilities.util_logger import logger
from utilities.util_process import run_logged_process
from utilities.util_shell import remove_shortcuts, shortcut_roots, start_explorer, stop_processes


_EXPLORER_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer"
_ONEDRIVE_CLSID = "{018D5C66-4533-4307-9B53-224DE2ED1FE6}"
_REGISTRY_VIEW = winreg.KEY_WOW64_64KEY
_ONEDRIVE_PROCESSES = ("*onedrive*", "FileCoAuth.exe", "FileSync*.exe", "Microsoft.SharePoint.exe")


def _environment_path(name):
    value = os.environ.get(name, "")
    if not value or not os.path.isabs(value):
        raise ValueError(f"Windows environment path {name} is missing or invalid.")
    return os.path.abspath(value)


def _clear_taskbar_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_SET_VALUE | _REGISTRY_VIEW) as key:
            winreg.DeleteValue(key, name)
        logger.info("Removed taskbar registry value: %s\\%s", path, name)
    except FileNotFoundError:
        logger.debug("Taskbar registry value is already absent: %s\\%s", path, name)


def _hide_task_view():
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _EXPLORER_KEY + r"\Advanced", 0,
                           winreg.KEY_SET_VALUE | _REGISTRY_VIEW) as key:
        winreg.SetValueEx(key, "ShowTaskViewButton", 0, winreg.REG_DWORD, 0)
    logger.info("Set ShowTaskViewButton to 0")


def _remove_registry_tree(hive, path):
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WRITE | _REGISTRY_VIEW) as key:
            names = [winreg.EnumKey(key, index) for index in range(winreg.QueryInfoKey(key)[0])]
        for name in names:
            _remove_registry_tree(hive, path + "\\" + name)
        winreg.DeleteKeyEx(hive, path, _REGISTRY_VIEW, 0)
        logger.info("Removed OneDrive registry key: %s\\%s", hive, path)
    except FileNotFoundError:
        logger.debug("OneDrive registry key is already absent: %s\\%s", hive, path)


def _file_present(path):
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise OSError(f"Expected an application file: {path}")
    return True


def _onedrive_application_roots():
    locations = [(_environment_path("LOCALAPPDATA"), os.path.join("Microsoft", "OneDrive"))]
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(variable):
            locations.append((_environment_path(variable), "Microsoft OneDrive"))
    roots = {}
    for parent, name in locations:
        path = checked_cleanup_path(os.path.join(parent, name), parent)
        try:
            attributes = os.lstat(path).st_file_attributes
        except FileNotFoundError:
            pass
        else:
            if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError(f"Refusing to stop processes from a redirected OneDrive installation: {path}")
        roots[os.path.normcase(path)] = path
    return list(roots.values())


def _onedrive_installed():
    if any(_file_present(os.path.join(root, "OneDrive.exe")) for root in _onedrive_application_roots()):
        return True
    registration = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\OneDriveSetup.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, registration, 0, winreg.KEY_READ | view):
                    return True
            except FileNotFoundError:
                continue
    return False


def _uninstall_onedrive(system_root):
    for directory in ("SysWOW64", "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"):
        installer = os.path.join(system_root, directory, "OneDriveSetup.exe")
        if _file_present(installer):
            result = run_logged_process([installer, "/uninstall"], label="OneDrive uninstaller",
                                        encoding=None, timeout=300)
            if result.returncode not in (0, 3010):
                raise RuntimeError(f"OneDrive uninstaller exited with code {result.returncode}.")
            if result.returncode == 3010:
                logger.info("OneDrive removal requires a restart.")
            return
    if _onedrive_installed():
        raise RuntimeError("OneDrive is still installed, but no supported Windows OneDrive uninstaller was found.")
    logger.info("OneDrive and its Windows uninstallers are already absent.")


def _remove_outlook_directories(program_files):
    windows_apps = os.path.join(program_files, "WindowsApps")
    try:
        with os.scandir(windows_apps) as folders:
            targets = [entry.path for entry in folders
                       if entry.name.casefold().startswith("microsoft.outlookforwindows")
                       and entry.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        logger.debug("WindowsApps directory is absent: %s", windows_apps)
        return []
    failures = []
    for target in targets:
        try:
            checked_cleanup_path(target, windows_apps)
            remove_path(target, windows_apps, take_ownership=True)
        except Exception as error:
            logger.exception("Unable to remove Outlook application directory: %s", target)
            failures.append(f"{target}: {error}")
    return failures


def _remove_cache_files(local_appdata):
    failures = []
    explorer = os.path.join(local_appdata, "Microsoft", "Windows", "Explorer")
    try:
        with os.scandir(explorer) as entries:
            targets = [entry.path for entry in entries
                       if entry.name.casefold().startswith(("iconcache", "thumbcache"))
                       and not entry.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        logger.debug("Explorer cache directory is absent: %s", explorer)
        return failures
    for target in targets:
        try:
            remove_path(target, explorer)
        except Exception as error:
            logger.exception("Unable to remove Explorer cache: %s", target)
            failures.append(f"{target}: {error}")
    return failures


def _remove_outlook_onedrive():
    system_root = _environment_path("SystemRoot")
    program_files = _environment_path("ProgramW6432" if os.environ.get("ProgramW6432") else "ProgramFiles")
    local_appdata = _environment_path("LOCALAPPDATA")
    program_data = _environment_path("ProgramData")
    system_drive = os.path.splitdrive(system_root)[0] + os.sep
    onedrive_roots = _onedrive_application_roots()
    roots, failures = shortcut_roots()

    def perform(label, action, *args, **kwargs):
        logger.info("%s", label)
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

    outlook_stopped = perform("Stopping Outlook processes", stop_processes, ["*outlook*"])
    outlook_removed = perform("Removing Outlook app packages and provisioning", remove_outlook_packages)
    perform("Removing Outlook shortcuts", remove_shortcuts, roots,
            ["*OUTLOOK.EXE*", "*Microsoft.Office.Outlook*", "*Microsoft.OutlookForWindows*", "*Outlook*"])
    onedrive_stopped = perform("Stopping OneDrive processes", stop_processes, _ONEDRIVE_PROCESSES,
                              allowed_executable_roots=onedrive_roots)
    onedrive_uninstalled = onedrive_stopped and perform("Uninstalling OneDrive", _uninstall_onedrive, system_root)
    try:
        explorer_stopped = perform("Stopping Explorer", stop_processes, ["explorer.exe"])
        if explorer_stopped:
            if outlook_stopped and outlook_removed:
                perform("Removing remaining Outlook application directories", _remove_outlook_directories, program_files)
            perform("Removing Explorer icon and thumbnail caches", _remove_cache_files, local_appdata)
        perform("Updating taskbar settings", _hide_task_view)
        for suffix in ("Taskband", "TaskbarMRU", "TaskBar", "Advanced"):
            for name in ("Favorites", "FavoritesResolve", "FavoritesChanges", "FavoritesRemovedChanges",
                         "TaskbarWinXP", "PinnedItems"):
                perform(f"Clearing {suffix}\\{name}", _clear_taskbar_value, _EXPLORER_KEY + "\\" + suffix, name)
        shell_directory = os.path.join(local_appdata, "Microsoft", "Windows", "Shell")
        perform("Removing taskbar layout override", remove_path,
                os.path.join(shell_directory, "LayoutModification.xml"), shell_directory)
        if onedrive_uninstalled:
            perform("Removing OneDrive shortcuts", remove_shortcuts, roots, ["*OneDrive.exe*", "*OneDrive*"])
            if explorer_stopped and perform("Stopping remaining OneDrive processes", stop_processes,
                                            _ONEDRIVE_PROCESSES, allowed_executable_roots=onedrive_roots):
                for parent, name in ((local_appdata, r"Microsoft\OneDrive"),
                                     (program_data, r"Microsoft\OneDrive"), (system_drive, "OneDriveTemp")):
                    target = os.path.join(parent, name)
                    perform(f"Removing OneDrive directory {target}", remove_path, target, parent)
            for hive, path in (
                (winreg.HKEY_CLASSES_ROOT, "CLSID\\" + _ONEDRIVE_CLSID),
                (winreg.HKEY_CLASSES_ROOT, "Wow6432Node\\CLSID\\" + _ONEDRIVE_CLSID),
                (winreg.HKEY_CURRENT_USER, _EXPLORER_KEY + "\\Desktop\\NameSpace\\" + _ONEDRIVE_CLSID),
            ):
                perform(f"Removing OneDrive integration {path}", _remove_registry_tree, hive, path)
        else:
            logger.warning("Skipping OneDrive cleanup because stopping or uninstalling OneDrive failed.")
    finally:
        perform("Starting Explorer", start_explorer)
    if failures:
        raise RuntimeError("Some Outlook/OneDrive removal operations failed:\n" + "\n".join(failures))


def main():
    ensure_admin()
    try:
        _remove_outlook_onedrive()
    except Exception as error:
        logger.exception("Outlook and OneDrive removal failed")
        show_error_popup(t("errors.outlook_onedrive_failed", {"error": error}), allow_continue=True)
        logger.warning("Continuing after incomplete Outlook and OneDrive removal")
        return
    logger.info("Outlook and OneDrive removal completed successfully.")


if __name__ == "__main__":
    main()
