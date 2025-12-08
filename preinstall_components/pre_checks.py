import os
import sys
import tempfile
import subprocess
from utilities.util_windows_check import check_windows_11_home_or_pro
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger



def _check_temp_writable() -> bool:
    temp_root = os.environ.get("TEMP", tempfile.gettempdir())
    talon_dir = os.path.join(temp_root, "talon")
    try:
        os.makedirs(talon_dir, exist_ok=True)
        test_path = os.path.join(talon_dir, "_write_test")
        with open(test_path, "w") as f:
            f.write("test")
        os.remove(test_path)
        return True
    except Exception as e:
        logger.error(f"Temp dir check failed: {e}")
        show_error_popup(
            f"Talon could not write files to {talon_dir}.\n"
            "Please free up disk space or check permissions.",
            allow_continue=True,
        )
        return False



def _run_test_script(script_path: str) -> bool:
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
        )
        output = result.stdout.strip()
        logger.debug(f"Test script output: {output}")
        if result.returncode == 0 and "Hello, World!" in output:
            return True
    except Exception as e:
        logger.error(f"Running test PowerShell script failed: {e}")
    show_error_popup(
        "Failed to run test PowerShell script. Powershell may be disabled.",
        allow_continue=True,
    )
    return False


def _check_onedrive_running() -> None:
    """Checks if OneDrive is running and warns the user."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq OneDrive.exe"],
            capture_output=True,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
        )
        # tasklist output contains the image name if found
        if "OneDrive.exe" in result.stdout:
            logger.warning("OneDrive detected running.")
            show_error_popup(
                "OneDrive is currently running.\n\n"
                "Running Talon while OneDrive is active may result in accidental data loss (Issue #217).\n"
                "It is HIGHLY recommended that you sign out and close OneDrive completely before continuing.",
                allow_continue=True,
            )
    except Exception as e:
        logger.error(f"OneDrive check failed: {e}")


def main() -> None:
    check_windows_11_home_or_pro()
    _check_onedrive_running()
    _check_temp_writable()



if __name__ == "__main__":
    main()