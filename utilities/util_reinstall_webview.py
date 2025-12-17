import subprocess, os
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger




def reinstall_webview(webview_installer_path: str,) -> int:
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
    except Exception as e:
        logger.exception(f"Failed to start WebView2 installer: {e}")
        show_error_popup(
            f"Error launching WebView2 installer:\n{e}",
        )
        raise