import ctypes
import msvcrt
import os
import tempfile
from ctypes import wintypes
from utilities.util_windows_check import check_windows_11_home_or_pro
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger
from configuration_components.localization import t

def _check_temp_writable() -> bool:
    temp_root = os.environ.get("TEMP", tempfile.gettempdir())
    talon_dir = os.path.join(temp_root, "talon")
    try:
        os.makedirs(talon_dir, exist_ok=True)
        fd, test_path = tempfile.mkstemp(prefix="talon_write_", dir=talon_dir)
        try:
            with os.fdopen(fd, "w") as f:
                f.write("test")
        finally:
            try:
                os.remove(test_path)
            except FileNotFoundError:
                logger.debug("Temporary preflight file was already removed: %s", test_path)
        return True
    except Exception as e:
        logger.exception(f"Temp dir check failed: {e}")
        show_error_popup(
            t("errors.temp_unwritable", {"talon_dir": talon_dir}),
            allow_continue=False,
        )
        return False


def _check_native_output() -> bool:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        kernel32.WriteFile.restype = wintypes.BOOL
        output = kernel32.GetStdHandle(wintypes.DWORD(-11))
        if output == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        message = b"Hello, World!\r\n"

        def write(handle):
            remaining = message
            while remaining:
                written = wintypes.DWORD()
                if not kernel32.WriteFile(handle, remaining, len(remaining), ctypes.byref(written), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not written.value:
                    raise OSError("WriteFile wrote no preflight output.")
                remaining = remaining[written.value:]

        if output:
            write(output)
        else:
            logger.debug("No console output handle; checking native output through a temporary file")
            with tempfile.TemporaryFile() as temporary_output:
                write(msvcrt.get_osfhandle(temporary_output.fileno()))
        logger.info("Native preflight output completed: %s", message.decode("ascii").strip())
        return True
    except Exception as error:
        logger.exception("Native preflight output check failed")
        show_error_popup(t("errors.native_output_failed", {"error": error}), allow_continue=False)
        return False


def main() -> None:
    check_windows_11_home_or_pro()
    if not _check_temp_writable():
        raise SystemExit(1)
    if not _check_native_output():
        raise SystemExit(1)

if __name__ == "__main__":
    main()
