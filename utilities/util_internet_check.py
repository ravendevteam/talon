import time
import ssl
import certifi
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup


def ensure_internet(max_attempts: int = 3, url: str = "https://ravendevteam.org", timeout: int = 5, allow_continue: bool = False,) -> bool:
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Checking internet connectivity (attempt {attempt}/{max_attempts})...")
            req = Request(url, headers={"User-Agent": "Talon/1.0"})
            with urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
                status = getattr(resp, "status", None) or getattr(resp, "code", None)
                logger.debug(f"Internet check HTTP status: {status}")
                if status is None or 200 <= int(status) < 500:
                    logger.info("Internet connectivity confirmed.")
                    return True
        except (HTTPError, URLError, Exception) as e:
            logger.warning(f"Internet check failed: {e}")
            if attempt < max_attempts:
                time.sleep(1)
    if allow_continue:
        show_error_popup(
            "No internet connection detected.\n\n"
            "Talon can continue without internet. If you proceed now, the browser installation and webview2 reinstallation steps will be skipped.\n\n"
            "Options:\n"
            "- Connect to the internet and run Talon again to install your browser automatically.\n"
            "- Or click Continue to proceed without a browser install (you can install a browser later).",
            allow_continue=True,
        )
    else:
        show_error_popup(
            "No internet connection detected.\n"
            "An active internet connection is required to run Talon in non-headless mode.\n",
            allow_continue=False,
        )
    return False
