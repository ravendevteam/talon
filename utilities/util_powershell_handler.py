import subprocess
import threading
from typing import Optional, Sequence, Union
from utilities.util_logger import logger
from utilities.util_process import wait_for_logged_process



def run_powershell_command(
    command: Union[str, Sequence[str]],
    *,
    cancel_event: Optional[threading.Event] = None,
) -> int:
    if not isinstance(command, str):
        command = "".join(command)
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
    ]
    logger.info(f"Launching PowerShell command: {command}")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
    except Exception as e:
        logger.exception(f"Failed to start PowerShell command: {e}")
        raise
    rc = wait_for_logged_process(
        proc,
        "PCOMMAND",
        cancel_event=cancel_event,
    )
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("PowerShell command was cancelled")
    if rc != 0:
        logger.error(f"PowerShell exited with code {rc}")
        raise RuntimeError(f"PowerShell command failed (code {rc})")
    else:
        logger.debug(f"PowerShell completed successfully (code {rc})")
    return rc
