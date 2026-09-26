import ctypes
import fnmatch
import os
import stat
import uuid
from contextlib import contextmanager
from ctypes import wintypes
from functools import lru_cache

from utilities.util_logger import logger


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


@lru_cache(maxsize=1)
def _libraries():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    signatures = (
        (kernel.CreateToolhelp32Snapshot, [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        (kernel.Process32FirstW, [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)], wintypes.BOOL),
        (kernel.Process32NextW, [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)], wintypes.BOOL),
        (kernel.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (kernel.QueryFullProcessImageNameW, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        (kernel.TerminateProcess, [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        (kernel.WaitForSingleObject, [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        (kernel.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
        (kernel.GetWindowsDirectoryW, [wintypes.LPWSTR, wintypes.UINT], wintypes.UINT),
        (kernel.SetFileAttributesW, [wintypes.LPCWSTR, wintypes.DWORD], wintypes.BOOL),
        (kernel.DeleteFileW, [wintypes.LPCWSTR], wintypes.BOOL),
        (ole.CoInitializeEx, [ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
        (ole.CoUninitialize, [], None),
        (ole.CoCreateInstance, [ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long),
        (ole.CoTaskMemFree, [ctypes.c_void_p], None),
        (shell.SHGetKnownFolderPath, [ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long),
        (shell.ShellExecuteExW, [ctypes.POINTER(_SHELLEXECUTEINFO)], wintypes.BOOL),
        (shell.SHChangeNotify, [wintypes.LONG, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p], None),
    )
    for function, arguments, result in signatures:
        function.argtypes = arguments
        function.restype = result
    return kernel, ole, shell


def _failure(failures, message, error):
    detail = f"{message}: {error}"
    logger.error(detail, exc_info=(type(error), error, error.__traceback__))
    failures.append(detail)


def _close_handle(kernel, handle, failures):
    if not kernel.CloseHandle(handle):
        _failure(failures, "Unable to close Windows handle", ctypes.WinError(ctypes.get_last_error()))


def _matches(value, patterns):
    return any(fnmatch.fnmatchcase(value.casefold(), pattern.casefold()) for pattern in patterns)


def _executable_path(path):
    path = os.path.expandvars(os.fspath(path))
    if not path or not os.path.isabs(path) or not os.path.splitdrive(path)[0]:
        raise ValueError(f"Executable path must be absolute: {path!r}")
    path = os.path.normcase(os.path.realpath(path))
    if path.startswith("\\\\?\\unc\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return path


def _executable_allowed(path, allowed_roots, exact_paths, names=None):
    if allowed_roots is None and exact_paths is None:
        return True
    if not path:
        return False
    path = _executable_path(path)
    if exact_paths is not None and path in exact_paths:
        return True
    if names is not None and os.path.basename(path).casefold() not in names:
        return False
    for root in allowed_roots or ():
        if os.path.splitdrive(path)[0] == os.path.splitdrive(root)[0]:
            if path != root and os.path.commonpath((path, root)) == root:
                return True
    return False


def _request_process_close(process_id, failures):
    requested = False
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user.EnumWindows.restype = wintypes.BOOL
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype = wintypes.DWORD
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.PostMessageW.restype = wintypes.BOOL

        @callback_type
        def close_window(window, _):
            nonlocal requested
            try:
                owner = wintypes.DWORD()
                if not user.GetWindowThreadProcessId(window, ctypes.byref(owner)):
                    error = ctypes.get_last_error()
                    if error != 1400:
                        raise ctypes.WinError(error)
                elif owner.value == process_id:
                    if user.PostMessageW(window, 0x0010, 0, 0):
                        requested = True
                    else:
                        error = ctypes.get_last_error()
                        if error != 1400:
                            raise ctypes.WinError(error)
            except Exception as error:
                _failure(failures, f"Unable to close window for process {process_id}", error)
            return True

        if not user.EnumWindows(close_window, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if requested:
            logger.info("Requested graceful shutdown of process %s", process_id)
    except Exception as error:
        _failure(failures, f"Unable to request graceful shutdown of process {process_id}", error)
    return requested


def stop_processes(patterns, *, allowed_executable_roots=None, exact_executable_paths=None,
                   graceful_timeout_ms=0):
    failures = []
    if not isinstance(graceful_timeout_ms, int) or not 0 <= graceful_timeout_ms < 0xFFFFFFFF:
        raise ValueError("Graceful shutdown timeout must be a nonnegative finite number of milliseconds")
    allowed_roots = None if allowed_executable_roots is None else tuple(map(_executable_path, allowed_executable_roots))
    exact_paths = None if exact_executable_paths is None else frozenset(map(_executable_path, exact_executable_paths))
    kernel, _, _ = _libraries()
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        _failure(failures, "Unable to enumerate running processes", ctypes.WinError(ctypes.get_last_error()))
        return failures
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            name = entry.szExeFile
            if _matches(name, patterns) or _matches(os.path.splitext(name)[0], patterns):
                handle = kernel.OpenProcess(0x00101001, False, entry.th32ProcessID)
                if not handle:
                    error = ctypes.get_last_error()
                    if error == 87:
                        logger.debug("Process already exited: %s (%s)", name, entry.th32ProcessID)
                    else:
                        _failure(failures, f"Unable to open process {name} ({entry.th32ProcessID})", ctypes.WinError(error))
                else:
                    try:
                        actual_name = ctypes.create_unicode_buffer(32768)
                        capacity = wintypes.DWORD(len(actual_name))
                        if not kernel.QueryFullProcessImageNameW(handle, 0, actual_name, ctypes.byref(capacity)):
                            error = ctypes.get_last_error()
                            state = kernel.WaitForSingleObject(handle, 0)
                            if state == 0xFFFFFFFF:
                                raise ctypes.WinError(ctypes.get_last_error())
                            if state != 0:
                                raise ctypes.WinError(error)
                            logger.debug("Process already exited: %s (%s)", name, entry.th32ProcessID)
                        elif os.path.basename(actual_name.value).casefold() != name.casefold():
                            logger.warning("Skipping reused process ID %s: %s", entry.th32ProcessID, actual_name.value)
                        elif not _executable_allowed(actual_name.value, allowed_roots, exact_paths):
                            logger.debug("Leaving process outside selected executable paths: %s (%s)", actual_name.value, entry.th32ProcessID)
                        else:
                            state = kernel.WaitForSingleObject(handle, 0)
                            if state == 0xFFFFFFFF:
                                raise ctypes.WinError(ctypes.get_last_error())
                            if state == 0:
                                logger.debug("Process already exited: %s (%s)", name, entry.th32ProcessID)
                            else:
                                if graceful_timeout_ms and _request_process_close(entry.th32ProcessID, failures):
                                    state = kernel.WaitForSingleObject(handle, graceful_timeout_ms)
                                    if state == 0xFFFFFFFF:
                                        raise ctypes.WinError(ctypes.get_last_error())
                                if state != 0:
                                    if not kernel.TerminateProcess(handle, 1):
                                        error = ctypes.get_last_error()
                                        if kernel.WaitForSingleObject(handle, 0) != 0:
                                            raise ctypes.WinError(error)
                                wait_result = kernel.WaitForSingleObject(handle, 10000)
                                if wait_result == 0xFFFFFFFF:
                                    raise ctypes.WinError(ctypes.get_last_error())
                                if wait_result != 0:
                                    raise TimeoutError(f"Process did not exit within 10 seconds (wait result {wait_result})")
                                logger.info("Stopped process %s (%s)", name, entry.th32ProcessID)
                    except Exception as error:
                        _failure(failures, f"Unable to stop process {name} ({entry.th32ProcessID})", error)
                    finally:
                        _close_handle(kernel, handle, failures)
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != 18:
            _failure(failures, "Unable to finish process enumeration", ctypes.WinError(error))
    finally:
        _close_handle(kernel, snapshot, failures)
    return failures


def _check_hresult(result):
    if result < 0:
        raise ctypes.WinError(result)


@contextmanager
def _com_apartment():
    _, ole, _ = _libraries()
    result = ole.CoInitializeEx(None, 2)
    if result != -2147417850:
        _check_hresult(result)
    try:
        yield ole
    finally:
        if result >= 0:
            ole.CoUninitialize()


def _com_method(pointer, index, result, *arguments):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(table[index])


def _read_shortcut(path, ole, *, structured=False):
    link = ctypes.c_void_p()
    persisted = ctypes.c_void_p()
    clsid = _GUID.parse("00021401-0000-0000-c000-000000000046")
    iid = _GUID.parse("000214f9-0000-0000-c000-000000000046")
    persist_iid = _GUID.parse("0000010b-0000-0000-c000-000000000046")
    try:
        _check_hresult(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link)))
        query = _com_method(link, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
        _check_hresult(query(link, ctypes.byref(persist_iid), ctypes.byref(persisted)))
        load = _com_method(persisted, 5, ctypes.c_long, wintypes.LPCWSTR, wintypes.DWORD)
        _check_hresult(load(persisted, path, 0))
        target = ctypes.create_unicode_buffer(32768)
        arguments = ctypes.create_unicode_buffer(32768)
        icon = ctypes.create_unicode_buffer(32768)
        icon_index = ctypes.c_int()
        get_path = _com_method(link, 3, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        get_arguments = _com_method(link, 10, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int)
        get_icon = _com_method(link, 16, ctypes.c_long, wintypes.LPWSTR, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
        _check_hresult(get_path(link, target, len(target), None, 4))
        _check_hresult(get_arguments(link, arguments, len(arguments)))
        _check_hresult(get_icon(link, icon, len(icon), ctypes.byref(icon_index)))
        details = {
            "target": target.value,
            "arguments": arguments.value,
            "icon": icon.value,
            "name": os.path.splitext(os.path.basename(path))[0],
        }
        return details if structured else " ".join(details.values())
    finally:
        for pointer in (persisted, link):
            if pointer:
                _com_method(pointer, 2, wintypes.ULONG)(pointer)


def shortcut_roots():
    failures = []
    roots = []
    _, ole, shell = _libraries()
    folders = (
        ("Common Programs", "0139d44e-6afe-49f2-8690-3dafcae6ffb8"),
        ("Programs", "a77f5d77-2e2b-44c3-a6a2-aba601054a51"),
        ("Public Desktop", "c4aa340d-f20f-4863-afef-f87ef2e6ba25"),
        ("Desktop", "b4bfcc3a-db2c-424c-b029-7fe99a87c641"),
    )
    for name, identifier in folders:
        path = ctypes.c_void_p()
        try:
            guid = _GUID.parse(identifier)
            _check_hresult(shell.SHGetKnownFolderPath(ctypes.byref(guid), 0x00004000, None, ctypes.byref(path)))
            value = ctypes.wstring_at(path)
            if value and value not in roots:
                roots.append(value)
        except Exception as error:
            _failure(failures, f"Unable to locate {name} shortcuts", error)
        finally:
            if path:
                ole.CoTaskMemFree(path)
    return roots, failures


def _checked_shortcut_path(root, path):
    root = os.path.normcase(os.path.abspath(root))
    path = os.path.normcase(os.path.abspath(path))
    if os.path.commonpath((root, path)) != root:
        raise ValueError(f"Shortcut is outside its search root: {path}")
    current = root
    for part in ("", *os.path.relpath(path, root).split(os.sep)):
        current = os.path.join(current, part)
        details = os.lstat(current)
        if getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Refusing to follow shortcut reparse point: {current}")
    return details


def remove_shortcuts(roots, patterns=(), *, allowed_executable_roots=None,
                     executable_names=None, exact_executable_paths=None):
    failures = []
    allowed_roots = None if allowed_executable_roots is None else tuple(map(_executable_path, allowed_executable_roots))
    exact_paths = None if exact_executable_paths is None else frozenset(map(_executable_path, exact_executable_paths))
    names = None if executable_names is None else frozenset(name.casefold() for name in executable_names)
    restricted = allowed_roots is not None or exact_paths is not None
    if allowed_roots is not None and names is None:
        raise ValueError("Executable names are required when selecting shortcuts by executable root")
    if names is not None and not restricted:
        raise ValueError("Shortcut executable names require selected executable paths or roots")
    kernel, _, _ = _libraries()
    try:
        with _com_apartment() as ole:
            for root in roots:
                root = os.path.abspath(root)
                try:
                    if not stat.S_ISDIR(_checked_shortcut_path(root, root).st_mode):
                        raise ValueError(f"Shortcut search root is not a directory: {root}")
                except FileNotFoundError:
                    logger.debug("Shortcut directory is absent: %s", root)
                    continue
                except Exception as error:
                    _failure(failures, f"Unable to inspect shortcut directory {root}", error)
                    continue
                def scan_error(error):
                    _failure(failures, f"Unable to scan shortcut directory {root}", error)
                for directory, subdirectories, filenames in os.walk(root, followlinks=False, onerror=scan_error):
                    for name in list(subdirectories):
                        try:
                            _checked_shortcut_path(root, os.path.join(directory, name))
                        except Exception as error:
                            subdirectories.remove(name)
                            _failure(failures, f"Skipping shortcut directory {os.path.join(directory, name)}", error)
                    for name in filenames:
                        if not name.casefold().endswith(".lnk"):
                            continue
                        path = os.path.join(directory, name)
                        try:
                            _checked_shortcut_path(root, path)
                            if restricted:
                                data = _read_shortcut(path, ole, structured=True)
                                matched = _executable_allowed(data["target"], allowed_roots, exact_paths, names)
                            else:
                                matched = _matches(_read_shortcut(path, ole), patterns)
                            if matched:
                                details = _checked_shortcut_path(root, path)
                                attributes = details.st_file_attributes
                                if attributes & stat.FILE_ATTRIBUTE_READONLY:
                                    if not kernel.SetFileAttributesW(path, attributes & ~stat.FILE_ATTRIBUTE_READONLY):
                                        raise ctypes.WinError(ctypes.get_last_error())
                                if not kernel.DeleteFileW(path):
                                    raise ctypes.WinError(ctypes.get_last_error())
                                logger.info("Removed shortcut: %s", path)
                        except FileNotFoundError:
                            logger.debug("Shortcut was already removed: %s", path)
                        except Exception as error:
                            _failure(failures, f"Unable to process shortcut {path}", error)
    except Exception as error:
        _failure(failures, "Unable to initialize shortcut inspection", error)
    return failures


def refresh_shell():
    failures = []
    try:
        _, _, shell = _libraries()
        shell.SHChangeNotify(0x08000000, 0x00003000, None, None)
        logger.info("Requested Windows Shell refresh")
    except Exception as error:
        _failure(failures, "Unable to notify Windows Shell of changes", error)
    return failures


def start_explorer():
    failures = []
    kernel, _, shell = _libraries()
    info = _SHELLEXECUTEINFO()
    try:
        with _com_apartment():
            directory = ctypes.create_unicode_buffer(32768)
            length = kernel.GetWindowsDirectoryW(directory, len(directory))
            if not length:
                raise ctypes.WinError(ctypes.get_last_error())
            if length >= len(directory):
                raise OSError("Windows directory exceeds the native path buffer")
            info.cbSize = ctypes.sizeof(info)
            info.fMask = 0x00000540
            info.lpVerb = "open"
            info.lpFile = os.path.join(directory.value, "explorer.exe")
            info.nShow = 1
            if not shell.ShellExecuteExW(ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            logger.info("Started Windows Explorer")
    except Exception as error:
        _failure(failures, "Unable to start Windows Explorer", error)
    finally:
        if info.hProcess:
            _close_handle(kernel, info.hProcess, failures)
    return failures
