import ctypes
import os
import stat
from contextlib import ExitStack, contextmanager, nullcontext
from ctypes import wintypes

from utilities.util_logger import logger


class _Luid(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class _TokenPrivileges(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("luid", _Luid), ("attributes", wintypes.DWORD)]


class _Trustee(ctypes.Structure):
    _fields_ = [
        ("multiple", ctypes.c_void_p), ("operation", wintypes.DWORD),
        ("form", wintypes.DWORD), ("kind", wintypes.DWORD), ("name", ctypes.c_void_p),
    ]


class _ExplicitAccess(ctypes.Structure):
    _fields_ = [
        ("permissions", wintypes.DWORD), ("mode", wintypes.DWORD),
        ("inheritance", wintypes.DWORD), ("trustee", _Trustee),
    ]


def _check(result, operation, status=False):
    code = result if status else ctypes.get_last_error()
    failed = result != 0 if status else not result
    if failed:
        raise ctypes.WinError(code, f"{operation}: {ctypes.FormatError(code).strip()}")
    return result


@contextmanager
def _ownership_access():
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    pointer_out = ctypes.POINTER(pointer)
    signatures = {
        "OpenProcessToken": (wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD, pointer_out]),
        "LookupPrivilegeValueW": (wintypes.BOOL, [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(_Luid)]),
        "AdjustTokenPrivileges": (wintypes.BOOL, [wintypes.HANDLE, wintypes.BOOL,
            ctypes.POINTER(_TokenPrivileges), wintypes.DWORD, ctypes.POINTER(_TokenPrivileges),
            ctypes.POINTER(wintypes.DWORD)]),
        "ConvertStringSidToSidW": (wintypes.BOOL, [wintypes.LPCWSTR, pointer_out]),
        "GetNamedSecurityInfoW": (wintypes.DWORD, [wintypes.LPCWSTR, wintypes.DWORD,
            wintypes.DWORD, pointer_out, pointer_out, pointer_out, pointer_out, pointer_out]),
        "SetNamedSecurityInfoW": (wintypes.DWORD, [wintypes.LPWSTR, wintypes.DWORD,
            wintypes.DWORD, pointer, pointer, pointer, pointer]),
        "SetEntriesInAclW": (wintypes.DWORD, [wintypes.DWORD,
            ctypes.POINTER(_ExplicitAccess), pointer, pointer_out]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(security, name)
        function.restype, function.argtypes = result, arguments
    kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], wintypes.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [pointer], pointer

    def free(memory):
        if kernel.LocalFree(memory):
            raise ctypes.WinError(ctypes.get_last_error())

    with ExitStack() as resources:
        token = pointer()
        _check(security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0028, ctypes.byref(token)),
               "OpenProcessToken")
        resources.callback(lambda: _check(kernel.CloseHandle(token), "CloseHandle(token)"))
        privilege = _TokenPrivileges(count=1, attributes=2)
        _check(security.LookupPrivilegeValueW(None, "SeTakeOwnershipPrivilege", ctypes.byref(privilege.luid)),
               "LookupPrivilegeValueW")
        previous, length = _TokenPrivileges(), wintypes.DWORD()
        ctypes.set_last_error(0)
        _check(security.AdjustTokenPrivileges(token, False, ctypes.byref(privilege),
               ctypes.sizeof(previous), ctypes.byref(previous), ctypes.byref(length)), "AdjustTokenPrivileges")
        error = ctypes.get_last_error()
        def restore_privileges():
            ctypes.set_last_error(0)
            _check(security.AdjustTokenPrivileges(token, False, ctypes.byref(previous), 0, None, None),
                   "Restore token privileges")
            restore_error = ctypes.get_last_error()
            if restore_error:
                raise ctypes.WinError(restore_error, "Unable to restore token privileges")
        resources.callback(restore_privileges)
        if error:
            raise ctypes.WinError(error, "Unable to enable SeTakeOwnershipPrivilege")
        administrators = pointer()
        _check(security.ConvertStringSidToSidW("S-1-5-32-544", ctypes.byref(administrators)),
               "ConvertStringSidToSidW")
        resources.callback(free, administrators)

        def grant(path):
            _check(security.SetNamedSecurityInfoW(path, 1, 1, administrators, None, None, None),
                   f"Take ownership of {path}", status=True)
            with ExitStack() as allocations:
                old_acl, descriptor, new_acl = pointer(), pointer(), pointer()
                _check(security.GetNamedSecurityInfoW(path, 1, 4, None, None,
                       ctypes.byref(old_acl), None, ctypes.byref(descriptor)),
                       f"Read permissions for {path}", status=True)
                allocations.callback(free, descriptor)
                access = _ExplicitAccess(permissions=0x001F01FF, mode=1, inheritance=0,
                                         trustee=_Trustee(form=0, kind=2, name=administrators))
                _check(security.SetEntriesInAclW(1, ctypes.byref(access), old_acl, ctypes.byref(new_acl)),
                       f"Build permissions for {path}", status=True)
                allocations.callback(free, new_acl)
                _check(security.SetNamedSecurityInfoW(path, 1, 4, None, None, new_acl, None),
                       f"Grant Administrators access to {path}", status=True)
            logger.debug("Granted cleanup access to %s", path)

        yield grant


def _cleanup_path_key(path):
    path = os.path.normcase(os.fsdecode(path))
    if path.startswith("\\\\?\\unc\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\") and len(path) > 6 and path[5:7] == ":\\":
        return path[4:]
    return path


def checked_cleanup_path(path, allowed_parent):
    target, parent = os.path.abspath(os.fspath(path)), os.path.abspath(os.fspath(allowed_parent))
    target_key, parent_key = _cleanup_path_key(target), _cleanup_path_key(parent)
    try:
        outside = target_key == parent_key or os.path.commonpath((target_key, parent_key)) != parent_key
    except ValueError:
        outside = True
    if outside:
        raise ValueError(f"Cleanup target is outside its allowed parent: {target} ({parent})")
    resolved_parent = _cleanup_path_key(os.path.realpath(parent))
    resolved_container = _cleanup_path_key(os.path.realpath(os.path.dirname(target)))
    try:
        redirected = os.path.commonpath((resolved_container, resolved_parent)) != resolved_parent
    except ValueError:
        redirected = True
    if redirected:
        raise ValueError(f"Cleanup target crosses a redirected directory: {target}")
    return target


def remove_path(path, allowed_parent, take_ownership=False):
    target = checked_cleanup_path(path, allowed_parent)
    try:
        os.lstat(target)
    except FileNotFoundError:
        logger.debug("Cleanup target is already absent: %s", target)
        return
    failures = []
    with _ownership_access() if take_ownership else nullcontext(None) as grant:
        def remove(entry):
            try:
                checked_cleanup_path(entry, allowed_parent)
                info = os.lstat(entry)
                attributes = info.st_file_attributes
                if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    if attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
                        os.rmdir(entry)
                    else:
                        os.unlink(entry)
                    logger.info("Removed cleanup link without following its target: %s", entry)
                    return
                shared_file = not stat.S_ISDIR(info.st_mode) and getattr(info, "st_nlink", 1) > 1
                if grant and not shared_file:
                    grant(entry)
                if attributes & stat.FILE_ATTRIBUTE_READONLY and not shared_file:
                    os.chmod(entry, stat.S_IWRITE)
                if stat.S_ISDIR(info.st_mode):
                    with os.scandir(entry) as children:
                        paths = [child.path for child in children]
                    for child in paths:
                        remove(child)
                    os.rmdir(entry)
                else:
                    os.unlink(entry)
                logger.info("Removed cleanup target: %s", entry)
            except FileNotFoundError:
                logger.debug("Cleanup target disappeared before removal: %s", entry)
            except Exception as error:
                logger.exception("Unable to remove cleanup target: %s", entry)
                failures.append(f"{entry}: {error}")
        remove(target)
    if failures:
        raise RuntimeError("Cleanup failed: " + "; ".join(failures))
