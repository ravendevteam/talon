import logging
import logging.handlers
import os
import sys
import tempfile
import threading
import traceback
import warnings



def _get_base_path() -> str:
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        exe = os.path.abspath(sys.argv[0])
        return os.path.dirname(exe)

    utilities_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(utilities_dir)



def _get_log_file_path(filename: str = 'talon.log') -> str:
    return os.path.join(_get_base_path(), filename)


def _fallback_log_file_path() -> str:
    directory = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "Talon")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "talon.log")


class _TalonFileHandler(logging.handlers.RotatingFileHandler):
    def handleError(self, record):
        error = sys.exc_info()
        previous_path = self.baseFilename
        fallback_path = os.path.abspath(_fallback_log_file_path())
        if os.path.normcase(previous_path) == os.path.normcase(fallback_path):
            raise RuntimeError(f"Unable to write Talon log: {previous_path}") from error[1]
        close_error = None
        try:
            self.close()
        except Exception:
            close_error = sys.exc_info()
        self.baseFilename = fallback_path
        self.stream = self._open()
        self._closed = False
        self.stream.write(f"Logging failed for {previous_path}; continuing in {fallback_path}.\n")
        self.stream.write("".join(traceback.format_exception(*error)))
        if close_error:
            self.stream.write("Unable to close the previous log stream:\n")
            self.stream.write("".join(traceback.format_exception(*close_error)))
        self.stream.flush()
        logging.FileHandler.emit(self, record)


def _qt_message_handler(message_type, context, message):
    from PyQt5.QtCore import QtDebugMsg, QtInfoMsg, QtWarningMsg, QtCriticalMsg, QtFatalMsg
    levels = {
        QtDebugMsg: logging.DEBUG,
        QtInfoMsg: logging.INFO,
        QtWarningMsg: logging.WARNING,
        QtCriticalMsg: logging.ERROR,
        QtFatalMsg: logging.CRITICAL,
    }
    logging.getLogger().log(
        levels.get(message_type, logging.WARNING),
        "Qt [%s] %s (%s:%s, %s)", context.category, message,
        context.file or "unknown", context.line, context.function or "unknown",
    )



def setup_logger(
    name: str = None,
    log_file: str = None,
    level: int = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5
) -> logging.Logger:
    level = logging.DEBUG if level is None else level
    level_name = os.environ.get('TALON_LOG_LEVEL')
    if level_name:
        level = getattr(logging, level_name.upper(), level)
    if log_file is None:
        log_file = _get_log_file_path()
    root = logging.getLogger(name) if name else logging.getLogger()
    root.setLevel(logging.DEBUG)
    requested_path = os.path.normcase(os.path.abspath(log_file))
    fh = next((handler for handler in root.handlers
               if isinstance(handler, _TalonFileHandler)
               and getattr(handler, "_talon_requested_path", None) == requested_path), None)
    setup_error = None
    if fh is None:
        try:
            fh = _TalonFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count,
                                   encoding="utf-8", errors="backslashreplace")
        except OSError:
            setup_error = sys.exc_info()
            fh = _TalonFileHandler(_fallback_log_file_path(), maxBytes=max_bytes,
                                   backupCount=backup_count, encoding="utf-8", errors="backslashreplace")
        fh._talon_requested_path = requested_path
        root.addHandler(fh)
    fh.setLevel(logging.DEBUG)
    fmt = (
        '%(asctime)s [%(levelname)s] %(name)s '
        '%(module)s.%(funcName)s:%(lineno)d [pid:%(process)d tid:%(thread)d '
        'threadName:%(threadName)s]: %(message)s'
    )
    datefmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(fmt, datefmt)
    fh.setFormatter(formatter)
    if sys.stdout is not None:
        ch = next((handler for handler in root.handlers if getattr(handler, "_talon_console", False)), None)
        if ch is None:
            ch = logging.StreamHandler(sys.stdout)
            ch._talon_console = True
            root.addHandler(ch)
        ch.setLevel(level)
        ch.setFormatter(formatter)
    if setup_error:
        root.warning("Unable to open log %s; logging to %s instead.", log_file, fh.baseFilename, exc_info=setup_error)
    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            root.info("Interrupted by user", exc_info=(exc_type, exc_value, exc_traceback))
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root.error("Uncaught exception",
                   exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = _handle_exception
    if hasattr(threading, 'excepthook'):
        def _thread_excepthook(args):
            root.error("Uncaught threading exception in '%s'", getattr(args.thread, "name", "unknown"),
                       exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        threading.excepthook = _thread_excepthook
    def _unraisable_exception(args):
        root.error("Unraisable exception: %s (%r)", args.err_msg or "callback or finalizer", args.object,
                   exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    sys.unraisablehook = _unraisable_exception
    from PyQt5.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)
    logging.captureWarnings(True)
    warnings.simplefilter('default')
    root.debug(
        f"Logger initialized (level={logging.getLevelName(level)}, "
        f"file={fh.baseFilename}, maxBytes={max_bytes}, backups={backup_count})"
    )
    return root



logger = setup_logger()
