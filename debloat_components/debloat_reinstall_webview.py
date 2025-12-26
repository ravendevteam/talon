import subprocess, os
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup


def main() -> int:
    webview_installer_path = os.path.join(os.path.dirname(__file__), "..", "external_scripts", "webview2.exe")
    logger.info("Reinstalling WebView2 runtime...")
    cmd = [webview_installer_path, "/silent", "/install",
    ]
    logger.info(f"Launching WebView2 installer: {webview_installer_path}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        stdout, stderr = proc.communicate()
        rc = proc.returncode
        logger.info(f'WebView2 installer return code: {rc}')
        logger.info(f'WebView2 installer stdout: {stdout}')
        logger.info(f'WebView2 installer stderr: {stderr}')
    except Exception as e:
        logger.exception(f"Failed to start WebView2 installer: {e}")
        # Idk if you want to add an error popup for this as its just a small thing