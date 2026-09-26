import sys
import threading
from contextlib import contextmanager
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt, QThread
from configuration_components.localization import t
from utilities.util_logger import logger


_headless_mode = False
_warning_count = 0
_warning_lock = threading.Lock()
_error_context = threading.local()


def set_headless_mode(enabled: bool):
    global _headless_mode
    _headless_mode = bool(enabled)


def reset_warning_count():
    global _warning_count
    with _warning_lock:
        _warning_count = 0


def record_warning():
    global _warning_count
    with _warning_lock:
        _warning_count += 1


def get_warning_count():
    with _warning_lock:
        return _warning_count


@contextmanager
def collect_recoverable_errors():
    previous = getattr(_error_context, "collect_recoverable", False)
    _error_context.collect_recoverable = True
    try:
        yield
    finally:
        _error_context.collect_recoverable = previous



class ErrorDialogManager(QObject):
    showDialog = pyqtSignal(str, bool, object)

    def __init__(self, app):
        super().__init__(app)
        self._pending = set()
        self._lock = threading.Lock()
        self._closed = False
        self.showDialog.connect(self._on_showDialog, Qt.QueuedConnection)
        app.aboutToQuit.connect(self.close)
        app.destroyed.connect(_clear_manager)

    def request(self, message, allow_continue, event):
        with self._lock:
            if self._closed:
                event.error = RuntimeError("Application closed before the error could be displayed")
                event.set()
                return
            self._pending.add(event)
        try:
            self.showDialog.emit(message, allow_continue, event)
        except BaseException:
            with self._lock:
                self._pending.discard(event)
            raise

    @pyqtSlot(str, bool, object)
    def _on_showDialog(self, message, allow_continue, event):
        with self._lock:
            if event not in self._pending:
                return
        result = False
        error = None
        try:
            result = _show_dialog_with_overlays(message, allow_continue)
        except BaseException as caught:
            error = caught
            logger.exception("Failed to display queued error dialog")
        finally:
            with self._lock:
                self._pending.discard(event)
                if not event.is_set():
                    event.result = result
                    event.error = error
                    event.set()

    @pyqtSlot()
    def close(self):
        with self._lock:
            self._closed = True
            for event in self._pending:
                event.error = RuntimeError("Application closed while displaying an error")
                event.set()
            self._pending.clear()

    def reopen(self):
        with self._lock:
            if self._pending:
                raise RuntimeError("Cannot reset error dialogs while a request is pending")
            self._closed = False



_manager = None


def _clear_manager():
    global _manager
    _manager = None



def initialize_error_dialogs():
    global _manager
    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError("Error dialogs must be initialized on the application thread")
    if _manager is None or _manager.parent() is not app:
        _manager = ErrorDialogManager(app)
    _manager.reopen()
    return _manager



def _show_dialog_direct(message, allow_continue):
    dialog = QDialog()
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dialog.setWindowTitle(t("errors.dialog_title"))
    dialog.setWindowModality(Qt.ApplicationModal)
    layout = QVBoxLayout(dialog)
    if len(message) > 600 or message.count("\n") > 8:
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(message)
        layout.addWidget(details)
        screen = dialog.screen().availableGeometry()
        dialog.resize(min(680, int(screen.width() * 0.8)), min(420, int(screen.height() * 0.8)))
    else:
        label = QLabel(message)
        label.setTextFormat(Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setWordWrap(True)
        layout.addWidget(label)
    btn_stop = QPushButton(t("errors.stop_installation"))
    btn_stop.clicked.connect(dialog.reject)
    button_layout = QHBoxLayout()
    button_layout.addWidget(btn_stop)
    if allow_continue:
        btn_continue = QPushButton(t("errors.continue_anyways"))
        btn_continue.clicked.connect(dialog.accept)
        button_layout.addWidget(btn_continue)
    layout.addLayout(button_layout)
    result = dialog.exec_()
    return result == QDialog.Accepted


def _show_dialog_with_overlays(message, allow_continue):
    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError("Error dialogs can only modify windows on the application thread")
    quit_on_close = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    overlay_states = []
    try:
        for window in app.topLevelWidgets():
            if window.objectName().startswith("overlay_"):
                overlay_states.append((window, window.isVisible()))
                window.hide()
        result = _show_dialog_direct(message, allow_continue)
        if result:
            for window, was_visible in overlay_states:
                if was_visible:
                    window.show()
        return result
    finally:
        app.setQuitOnLastWindowClosed(quit_on_close)



def show_error_popup(message, allow_continue=False):
    logger.error("%s", message, exc_info=sys.exc_info()[0] is not None)
    if (allow_continue and not _headless_mode
            and getattr(_error_context, "collect_recoverable", False)):
        record_warning()
        logger.warning("Continuing installation; this failure is included in the completion warnings")
        return True
    try:
        return _show_error_popup(message, allow_continue)
    except Exception:
        logger.exception("Failed to display error dialog")
        raise


def _show_error_popup(message, allow_continue=False):
    if _headless_mode:
        if sys.stderr is not None:
            try:
                print(message, file=sys.stderr, flush=True)
            except (OSError, ValueError):
                logger.warning("Unable to write headless error to stderr", exc_info=True)
        raise SystemExit(1)
    app = QApplication.instance()
    if app is None:
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Cannot create an application for an error dialog from a worker")
        app = QApplication(sys.argv)
    if QThread.currentThread() == app.thread():
        result = _show_dialog_with_overlays(message, allow_continue)
    else:
        if _manager is None:
            raise RuntimeError("Error dialogs were not initialized before starting the worker")
        event = threading.Event()
        event.result = False
        event.error = None
        _manager.request(message, allow_continue, event)
        event.wait()
        if event.error is not None:
            raise event.error
        result = event.result
    if not result:
        sys.exit(1)
    if allow_continue:
        record_warning()
    return True
