import subprocess
import threading
import time

from utilities.util_logger import logger


def wait_for_logged_process(
    proc,
    label,
    *,
    cancel_event=None,
    timeout=None,
    output_callback=None,
):
    stream_errors = []
    termination_failed = threading.Event()
    started = time.monotonic()
    timed_out = False

    def terminate(reason):
        try:
            if proc.poll() is None:
                logger.warning(f"Terminating {label}: {reason}")
                proc.terminate()
            return True
        except Exception:
            logger.exception(f"Failed to terminate {label}: {reason}")
            try:
                proc.kill()
                return True
            except Exception:
                logger.exception(f"Failed to kill {label}: {reason}")
                termination_failed.set()
                return False

    def stream(pipe, log_fn, stream_name):
        try:
            for line in iter(pipe.readline, ""):
                text = line.rstrip("\r\n")
                log_fn(f"{label} {stream_name}: {text}")
                if output_callback is not None:
                    output_callback(stream_name, text)
        except Exception as error:
            stream_errors.append(error)
            logger.exception(f"Failed to read {label} {stream_name}")
            terminate("output reader failed")
        finally:
            try:
                pipe.close()
            except Exception as error:
                stream_errors.append(error)
                logger.exception(f"Failed to close {label} {stream_name}")

    threads = []
    for pipe, log_fn, stream_name in (
        (proc.stdout, logger.info, "STDOUT"),
        (proc.stderr, logger.error, "STDERR"),
    ):
        reader = threading.Thread(
            target=stream,
            args=(pipe, log_fn, stream_name),
            daemon=True,
        )
        reader.start()
        threads.append(reader)
    try:
        while proc.poll() is None:
            if termination_failed.is_set():
                raise RuntimeError(f"Unable to stop {label}")
            if stream_errors:
                raise RuntimeError(f"Failed to capture all output from {label}") from stream_errors[0]
            if timeout is not None and time.monotonic() - started >= timeout:
                logger.error(f"{label} timed out after {timeout} seconds")
                timed_out = True
                proc.kill()
                break
            if cancel_event and cancel_event.is_set():
                if not terminate("external cancellation"):
                    raise RuntimeError(f"Unable to cancel {label}")
                break
            time.sleep(0.1)
        returncode = proc.wait()
        for reader in threads:
            reader.join()
    except BaseException:
        logger.exception(f"Failed while waiting for {label}")
        terminate("process monitoring failed")
        try:
            proc.wait(timeout=5)
        except BaseException:
            logger.exception(f"Failed to finish waiting for {label} during cleanup")
        for reader in threads:
            try:
                reader.join(timeout=5)
                if reader.is_alive():
                    logger.error(f"Output reader for {label} did not stop; output may be incomplete")
            except BaseException:
                logger.exception(f"Failed to join output reader for {label} during cleanup")
        raise
    if timed_out:
        raise subprocess.TimeoutExpired(proc.args, timeout)
    if stream_errors:
        raise RuntimeError(f"Failed to capture all output from {label}") from stream_errors[0]
    return returncode


def run_logged_process(command, *, label=None, check=False, timeout=None, **kwargs):
    label = label or (command if isinstance(command, str) else subprocess.list2cmdline(command))
    logger.info(f"Launching process: {label}")
    options = {"stdin": subprocess.DEVNULL, "text": True, "encoding": "utf-8", "errors": "replace", "bufsize": 1}
    options.update(kwargs)
    options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        proc = subprocess.Popen(command, **options)
    except Exception:
        logger.exception(f"Failed to start process: {label}")
        raise
    returncode = wait_for_logged_process(proc, label, timeout=timeout)
    result = subprocess.CompletedProcess(command, returncode)
    if returncode:
        logger.warning(f"{label} exited with code {returncode}")
    if check:
        result.check_returncode()
    return result
