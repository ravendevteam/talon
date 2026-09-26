import time
import ssl
import threading
from http.client import HTTPException
from queue import Empty, Queue
import certifi
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from utilities.util_logger import logger


def _probe_url(url, timeout, results):
    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        req = Request(url, headers={"User-Agent": "Talon/1.0"}, method="HEAD")
        try:
            try:
                response = urlopen(req, timeout=timeout, context=ssl_ctx)
            except HTTPError as error:
                response = error
            with response as resp:
                status = getattr(resp, "status", None) or getattr(resp, "code", None)
                logger.debug("Internet check HTTP status from %s: %s", url, status)
                reachable = status is None or (200 <= int(status) < 500 and int(status) != 407)
        except (URLError, OSError, HTTPException):
            logger.warning("Internet check failed for %s", url, exc_info=True)
            reachable = False
        results.put((reachable, None))
    except Exception as error:
        results.put((False, error))


def has_internet(max_attempts: int = 3, url: str = "https://raventechnologiesgroup.com", timeout: int = 5) -> bool:
    if max_attempts < 1 or timeout <= 0:
        raise ValueError("Internet check attempts and timeout must be positive.")
    targets = tuple(dict.fromkeys((url, "https://www.microsoft.com/", "https://community.chocolatey.org/")))
    deadline = time.monotonic() + max_attempts * timeout
    for attempt in range(max_attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        target = targets[attempt % len(targets)]
        results = Queue(maxsize=1)
        logger.info("Checking internet connectivity at %s (attempt %s/%s)", target, attempt + 1, max_attempts)
        threading.Thread(target=_probe_url, args=(target, min(timeout, remaining), results), daemon=True).start()
        try:
            reachable, error = results.get(timeout=max(0, min(timeout, deadline - time.monotonic())))
        except Empty:
            logger.warning("Internet check timed out for %s", target)
            continue
        if error is not None:
            raise error
        if reachable:
            logger.info("Internet connectivity confirmed via %s", target)
            return True
    logger.warning("Internet connectivity could not be confirmed; continuing with offline options")
    return False
