import os
import sys
import ctypes
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from configuration_components.localization import t



def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        logger.exception(f"Admin check failed: {e}")
        return False



def run_as_admin():
    if getattr(sys, 'frozen', False):
        executable = sys.executable
        params = ' '.join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        executable = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{script}"'] + [f'"{arg}"' for arg in sys.argv[1:]])
    cwd = os.getcwd()
    logger.info(f"Elevating: {executable} {params}")
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            cwd,
            1
        )
        if result <= 32:
            raise OSError(f"ShellExecuteW failed with code {result}")
    except Exception as e:
        logger.exception("Failed to relaunch with admin privileges")
        show_error_popup(t("errors.admin_elevation_failed", {"error": e}), allow_continue=False)
        sys.exit(1)



def ensure_admin():
    if not is_admin():
        logger.warning("Administrator privileges required; relaunching with UAC prompt...")
        run_as_admin()
        sys.exit(0)
    else:
        logger.debug("Running with Administrator privileges.")



if __name__ == "__main__":
    ensure_admin()
    logger.info("Already running as admin.")
