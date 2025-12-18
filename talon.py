import os
import subprocess
import sys
import threading
import argparse
from screens import load as load_screen
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, QEvent, QTimer, QMetaObject, Qt, Q_ARG, pyqtSignal
from utilities.util_admin_check import ensure_admin
from utilities.util_internet_check import ensure_internet
import preinstall_components.pre_checks as pre_checks
import debloat_components.debloat_execute_raven_scripts as debloat_execute_raven_scripts
import debloat_components.debloat_execute_external_scripts as debloat_execute_external_scripts
import debloat_components.debloat_browser_installation as debloat_browser_installation
import debloat_components.debloat_registry_tweaks as debloat_registry_tweaks
import debloat_components.debloat_configure_updates as debloat_configure_updates
import debloat_components.debloat_apply_background as debloat_apply_background
from ui_components.ui_base_full import UIBaseFull
from ui_components.ui_header_text import UIHeaderText
from ui_components.ui_title_text import UITitleText
from ui_components.ui_loading_spinner import UILoadingSpinner



_INSTALL_UI_BASE = None
DEBLOAT_STEPS = [
	(
		"execute-raven-scripts",
		"Executing initial debloating scripts...",
		debloat_execute_raven_scripts.main,
	),
	(
		"browser-installation",
		"Installing your chosen browser...",
		debloat_browser_installation.main,
	),
	(
		"execute-external-scripts",
		"Debloating Windows...",
		debloat_execute_external_scripts.main,
	),
	(
		"registry-tweaks",
		"Making some visual tweaks...",
		debloat_registry_tweaks.main,
	),
	(
		"configure-updates",
		"Configuring Windows Update policies...",
		debloat_configure_updates.main,
	),
	(
		"apply-background",
		"Setting your desktop background...",
		debloat_apply_background.main,
	),
]



def parse_args(argv=None):
	parser = argparse.ArgumentParser(description="Talon installer")
	parser.add_argument(
		"--developer-mode",
		action="store_true",
		help="Run without the installing overlay (still shows the browser selection and donation consideration screens).",
	)
	parser.add_argument(
		"--headless",
		action="store_true",
		help="Run unattended (no UI, no prompts, skip browser install, runs offline, no restart).",
	)
	parser.add_argument(
		"--config",
		dest="config",
		metavar="PATH",
		help="Pass a custom WinUtil configuration to use instead of the default Talon configuration.",
	)
	for slug, _, _ in DEBLOAT_STEPS:
		dest = f"skip_{slug.replace('-', '_')}_step"
		parser.add_argument(
			f"--skip-{slug}-step",
			dest=dest,
			action="store_true",
			help=f"Skip the {slug.replace('-', ' ')} step",
		)
	return parser.parse_args(argv)



def run_screen(module_name: str):
	logger.debug(f"Launching screen: {module_name}")
	try:
		mod = load_screen(module_name)
	except ImportError:
		script_file = f"{module_name}.py"
		script_path = os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			"screens",
			script_file,
		)
		try:
			subprocess.run([sys.executable, script_path], check=True)
		except Exception as e:
			logger.error(f"Failed to launch screen {script_file}: {e}")
			show_error_popup(
				f"Failed to launch screen '{module_name}'.\n{e}",
				allow_continue=False,
			)
			sys.exit(1)
		return
	try:
		mod.main()
	except SystemExit:
		pass
	except Exception as e:
		logger.exception(f"Exception in screen '{module_name}': {e}")
		show_error_popup(
			f"An unexpected error occurred in screen '{module_name}'.\n{e}",
			allow_continue=False,
		)
		sys.exit(1)



def _build_install_ui():
	app = QApplication.instance() or QApplication(sys.argv)
	base = UIBaseFull()
	for overlay in base.overlays:
		overlay.setWindowOpacity(0.8)
	overlay = base.primary_overlay
	title_label = UITitleText("Talon is installing", parent=overlay)
	UIHeaderText(
		"Please don't use your keyboard or mouse. You can watch as Talon works.",
		parent=overlay,
	)
	status_label = UIHeaderText("", parent=overlay, follow_parent_resize=False)

	class StatusResizer(QObject):
		def __init__(self, parent, label, bottom_margin):
			super().__init__(parent)
			self.parent = parent
			self.label = label
			self.bottom_margin = bottom_margin
			parent.installEventFilter(self)
			self._update_position()
		def eventFilter(self, obj, event):
			if obj is self.parent and event.type() == QEvent.Resize:
				self._update_position()
			return False
		def _update_position(self):
			w = self.parent.width()
			fm = self.label.fontMetrics()
			h = fm.height()
			y = self.parent.height() - self.bottom_margin - h
			self.label.setGeometry(0, y, w, h)

	StatusResizer(overlay, status_label, bottom_margin=title_label._top_margin)
	spinner = UILoadingSpinner(overlay, dim_background=False, dim_opacity=0.0, duration_ms=1800, block_input=True)

	class _SpinnerBus(QObject):
		start = pyqtSignal()
		stop = pyqtSignal()
		raiseit = pyqtSignal()
		set_msg = pyqtSignal(str)
	bus = _SpinnerBus()
	bus.start.connect(spinner.start, Qt.QueuedConnection)
     
	bus.stop.connect(spinner.stop, Qt.QueuedConnection)
	bus.raiseit.connect(spinner.raise_, Qt.QueuedConnection)
	bus.set_msg.connect(status_label.setText, Qt.QueuedConnection)

	base.show()
	status_label.raise_()
	spinner.raise_()
	return app, status_label, base, spinner, bus



def _update_status(bus, label: UIHeaderText, message: str):
	if label is None:
		print(message)
		return
	bus.set_msg.emit(message)
	bus.raiseit.emit()



def main(argv=None):
	args = parse_args(argv)
	if args.headless:
		args.developer_mode = True
		args.skip_browser_installation_step = True
	ensure_admin()
	pre_checks.main()
	if not args.headless:
		online = ensure_internet(allow_continue=True)
		if online:
			run_screen("screen_browser_select")
		else:
			args.skip_browser_installation_step = True
		run_screen("screen_donation_request")
	app = None
	status_label = None
	spinner = None
	bus = None
	if not args.developer_mode:
		global _INSTALL_UI_BASE
		app, status_label, _INSTALL_UI_BASE, spinner, bus = _build_install_ui()

	def debloat_sequence():
		if bus is not None:
			bus.start.emit()
			bus.raiseit.emit()
		for slug, message, func in DEBLOAT_STEPS:
			if getattr(args, f"skip_{slug.replace('-', '_')}_step"):
				logger.info(f"Skipping {slug} step")
				continue
			_update_status(bus, status_label, message)
			try:
				if func is debloat_execute_external_scripts.main:
					func(args.config)
				else:
					func()
			except Exception:
				if bus is not None:
					bus.stop.emit()
				return
		if args.headless:
			_update_status(bus, status_label, "Suppressing system restart due to --headless flag used")
			if bus is not None:
				bus.stop.emit()
			return
		else:
			_update_status(bus, status_label, "Restarting system...")
			if bus is not None:
				bus.stop.emit()
			subprocess.call(["shutdown", "/r", "/t", "0"])

	if args.developer_mode or args.headless:
		debloat_sequence()
	else:
		def start_thread():
			threading.Thread(target=debloat_sequence, daemon=True).start()
		QTimer.singleShot(0, start_thread)
		sys.exit(app.exec_())



if __name__ == "__main__":
	main()