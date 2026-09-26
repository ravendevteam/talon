import sys
import threading
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QtWidgets import QApplication

from configuration_components.preflight import run_configuration_preflight
from configuration_components.qt_bridge import ConfigurationBridge
from configuration_components.localization import LocalizationBridge, t
from utilities.util_error_popup import initialize_error_dialogs, show_error_popup
from utilities.util_logger import logger


class CheckSignals(QObject):
    checks_passed = pyqtSignal(bool)
    checks_failed = pyqtSignal(object)
    relaunching = pyqtSignal()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    initialize_error_dialogs()
    engine = QQmlApplicationEngine()
    bridge = ConfigurationBridge()
    i18n = LocalizationBridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("i18n", i18n)
    qml_path = Path(__file__).resolve().parents[1] / "ui" / "configuration" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if bridge.failed:
        raise SystemExit(1)
    if not engine.rootObjects():
        raise RuntimeError(f"Failed to load QML: {qml_path}")

    root = engine.rootObjects()[0]
    signals = CheckSignals()

    def _on_checks_passed(internet_available: bool):
        if bridge.failed:
            return
        try:
            bridge.set_internet_available(internet_available)
            root.setProperty("internetAvailable", bool(internet_available))
            root.setProperty("currentPage", 1)
        except BaseException as error:
            logger.exception("Unable to finish configuration preflight")
            _on_checks_failed(error)

    def _on_checks_failed(error):
        try:
            if isinstance(error, Exception) and not bridge.failed:
                show_error_popup(t("errors.start_plan_failed", {"error": error}), allow_continue=False)
        except SystemExit:
            logger.debug("Configuration failure was acknowledged")
        except BaseException:
            logger.exception("Unable to report configuration failure")
        finally:
            bridge.failed = True
            bridge.start_requested = False
            app.exit(1)

    signals.checks_passed.connect(_on_checks_passed)
    signals.checks_failed.connect(_on_checks_failed)
    signals.relaunching.connect(app.quit)

    def run_checks():
        try:
            internet_available, relaunched = run_configuration_preflight()
            if relaunched:
                signals.relaunching.emit()
                return
            signals.checks_passed.emit(internet_available)
        except BaseException as e:
            logger.error("Configuration preflight failed", exc_info=True)
            signals.checks_failed.emit(e)

    QTimer.singleShot(0, lambda: threading.Thread(target=run_checks, daemon=True).start())
    exit_code = app.exec_()
    if exit_code or bridge.failed:
        raise SystemExit(exit_code or 1)
    return bool(bridge.start_requested)


if __name__ == "__main__":
    main()
