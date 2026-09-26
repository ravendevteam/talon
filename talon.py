import os
import subprocess
import sys
import threading
import json
import tempfile
import time
import winreg
from types import SimpleNamespace
from utilities.util_logger import logger
from configuration_components import install_plan, step_catalog
from configuration_components.localization import t
from screens import load as load_screen
from utilities.util_error_popup import (
	collect_recoverable_errors, get_warning_count, initialize_error_dialogs, record_warning, reset_warning_count,
	set_headless_mode, show_error_popup,
)
from utilities.util_json import load_json_file
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, QEvent, QTimer, Qt, pyqtSignal
from utilities.util_admin_check import ensure_admin
import preinstall_components.pre_checks as pre_checks
import debloat_components.debloat_remove_edge as debloat_remove_edge
import debloat_components.debloat_uninstall_outlook_onedrive as debloat_uninstall_outlook_onedrive
import debloat_components.debloat_browser_installation as debloat_browser_installation
import debloat_components.debloat_program_installation as debloat_program_installation
import debloat_components.debloat_group_policy as debloat_group_policy
import debloat_components.debloat_execute_winutil as debloat_execute_winutil
import debloat_components.debloat_execute_win11debloat as debloat_execute_win11debloat
import debloat_components.debloat_execute_external_scripts as external_scripts
import debloat_components.debloat_registry_tweaks as debloat_registry_tweaks
import debloat_components.debloat_configure_updates as debloat_configure_updates
import debloat_components.debloat_apply_background as debloat_apply_background
from ui_components.ui_base_full import UIBaseFull
from ui_components.ui_header_text import UIHeaderText
from ui_components.ui_title_text import UITitleText
from ui_components.ui_loading_spinner import UILoadingSpinner

_INSTALL_UI_BASE = None
TALON_VERSION = "2026.9.26.18"
_COMPLETION_REGISTRY_PATH = r"Software\RavenTechnologiesGroup\Talon"
DEBLOAT_STEPS = [
	(
		"remove-edge-permanently",
		"app.install_overlay.removing_edge",
		debloat_remove_edge.main,
	),
	(
		"uninstall-outlook-onedrive",
		"app.install_overlay.uninstall_outlook_onedrive",
		debloat_uninstall_outlook_onedrive.main,
	),
	(
		"browser-installation",
		"app.install_overlay.browser_installation",
		debloat_browser_installation.main,
	),
	(
		"program-installation",
		"app.install_overlay.program_installation",
		debloat_program_installation.main,
	),
	(
		"debloat-windows-phase-one",
		"app.install_overlay.debloat_windows_phase_one",
		debloat_execute_winutil.main,
	),
	(
		"debloat-windows-phase-two",
		"app.install_overlay.debloat_windows_phase_two",
		debloat_execute_win11debloat.main,
	),
	(
		"registry-tweaks",
		"app.install_overlay.registry_tweaks",
		debloat_registry_tweaks.main,
	),
	(
		"configure-updates",
		"app.install_overlay.configure_updates",
		debloat_configure_updates.main,
	),
	(
		"group-policy",
		"app.install_overlay.group_policy",
		debloat_group_policy.main,
	),
	(
		"apply-background",
		"app.install_overlay.apply_background",
		debloat_apply_background.main,
	),
]


def command_line_help() -> str:
	lines = [
		f"Talon {TALON_VERSION}",
		"",
		"Usage:",
		"  Talon.exe [key=value ...]",
		"",
		"Separate arguments with spaces and use key=value.",
		"Quote the whole argument when a path contains spaces.",
		"Keys and boolean values are case-insensitive.",
		"Boolean values: true/1/yes/on or false/0/no/off.",
		"",
		"General arguments:",
		"  help=true             Show this help and exit. Default: false.",
		"  headless=true         Skip configuration UI and run unattended.",
		"                        Implies developer-mode. Default: false.",
		"  developer-mode=true   Hide the installation overlay and show console output.",
		"                        Still opens configuration unless headless=true.",
		"                        Default: false.",
		"  dry-run=true          Validate and preview steps without executing them.",
		"                        Use headless=true for a console preview. Default: false.",
		"  config=<path>         Load a local JSON file. URLs are not accepted.",
		"                        Default: no file; use UI settings or headless defaults.",
		"",
		"Step arguments (set any key below to true or false):",
		"Defaults below apply to headless runs WITHOUT a full Talon install plan.",
	]
	for slug, _, _ in DEBLOAT_STEPS:
		default = "false" if slug in step_catalog.OPTIONAL_STEP_SLUGS + ["browser-installation"] else "true"
		lines.append(f"  {slug}=<bool>")
		lines.append(f"    {step_catalog.step_text(slug)}. Default: {default}.")
	lines.extend([
		"",
		"Config files and step selection:",
		"  Export a full Talon install plan from Advanced Settings to reuse your choices.",
		"  With headless=true, a config containing 'items' is a full install plan:",
		"  omitted steps are disabled, and explicit CLI step arguments override its switches.",
		"  Enabled steps must have valid data; invalid plans are rejected before execution.",
		"  Older plans without program packages or Group Policy steps remain supported.",
		"",
		"  Config also accepts a WinUtil object/list or combined WinUtil/Win11Debloat JSON.",
		"  Headless runs with these configs use standard steps, with browser installation",
		"  skipped. Override unwanted steps with step-name=false.",
		"  A browser can be installed headlessly through a full plan with browser metadata.",
		"  Explicit CLI step arguments also override steps selected in the UI.",
		"  config supplies external-script settings in UI mode.",
		"",
		"Optional steps (off by default):",
		"  program-installation requires a nonempty 'chocolatey_packages' list of package",
		"  IDs in the config, for example: [\"7zip\", \"vlc\"].",
		"  group-policy requires a nonempty 'group_policy_changes' list and a supported",
		"  non-Home Windows edition. Configure these changes in Advanced Settings and",
		"  export a plan to obtain the required JSON format.",
		"",
		"Examples:",
		"  Talon.exe help=true",
		'  Talon.exe headless=true dry-run=true "config=C:\\Configs\\install plan.json"',
		'  Talon.exe headless=true "config=C:\\Configs\\install plan.json"',
		'  Talon.exe headless=true "config=C:\\Configs\\winutil.json" configure-updates=false',
		"  Talon.exe apply-background=false",
	])
	return "\n".join(lines)


def _show_command_line_help():
	stdout_name = str(getattr(sys.stdout, "name", "")).casefold()
	if sys.stdout is None or stdout_name in (os.devnull.casefold(), "nul:"):
		raise RuntimeError("Command-line help requires standard output. Run Talon.exe help=true from Command Prompt or PowerShell.")
	print(command_line_help(), flush=True)


def _launch_developer_console(raw_args) -> bool:
	script_path = os.path.abspath(__file__)
	python_cmd = [sys.executable, script_path] + list(raw_args)
	command_line = subprocess.list2cmdline(python_cmd)
	env = dict(os.environ)
	env["TALON_DEV_CONSOLE"] = "1"
	try:
		subprocess.Popen(
			["cmd.exe", "/k", command_line],
			creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
			env=env,
		)
		return True
	except Exception as e:
		logger.exception(f"Failed to launch developer console window: {e}")
		show_error_popup(
			t("errors.developer_console_failed", {"error": e}),
			allow_continue=False,
		)
		return False

def parse_args(argv=None):
	def _parse_bool(value: str) -> bool:
		v = str(value).strip().lower()
		if v in ("1", "true", "yes", "on"):
			return True
		if v in ("0", "false", "no", "off"):
			return False
		raise ValueError(f"Invalid boolean value: {value}")

	raw = sys.argv[1:] if argv is None else list(argv)
	args = SimpleNamespace()
	args.help = False
	args.developer_mode = False
	args.headless = False
	args.dry_run = False
	args.config = None
	args.step_overrides = {}
	for slug, _, _ in DEBLOAT_STEPS:
		setattr(args, f"skip_{slug.replace('-', '_')}_step", False)

	step_lookup = {slug: f"skip_{slug.replace('-', '_')}_step" for slug, _, _ in DEBLOAT_STEPS}
	alias_lookup = {
		"help": "help",
		"developer-mode": "developer_mode",
		"headless": "headless",
		"dry-run": "dry_run",
		"config": "config",
	}

	for token in raw:
		if "=" not in token:
			raise SystemExit(
				f"Invalid argument '{token}'. Use key=value format, e.g. configure-updates=false. Run help=true for usage."
			)
		key, value = token.split("=", 1)
		key = key.strip().lower()
		value = value.strip()

		if key in alias_lookup:
			attr = alias_lookup[key]
			if attr == "config":
				args.config = value
			else:
				setattr(args, attr, _parse_bool(value))
			continue

		if key in step_lookup:
			enabled = _parse_bool(value)
			args.step_overrides[key] = enabled
			setattr(args, step_lookup[key], not enabled)
			continue

		raise SystemExit(
			f"Unknown argument key '{key}'. Run help=true for usage. Supported keys: help, developer-mode, headless, dry-run, config, "
			+ ", ".join(step_lookup.keys())
		)

	return args

def run_screen(module_name: str):
	logger.debug(f"Launching screen: {module_name}")
	try:
		mod = load_screen(module_name)
		return mod.main()
	except SystemExit as error:
		if error.code not in (None, 0):
			logger.error("Screen %s exited with code %s", module_name, error.code, exc_info=True)
			raise
		else:
			logger.info("Screen %s closed", module_name)
		return False
	except Exception as e:
		logger.exception(f"Exception in screen '{module_name}': {e}")
		show_error_popup(
			t("errors.screen_unexpected", {"module_name": module_name, "error": str(e) or type(e).__name__}),
			allow_continue=False,
		)
		sys.exit(1)


def _load_install_plan() -> dict:
	return install_plan.load_install_plan()


def _build_execution_steps_from_plan(plan: dict):
	install_plan.validate_enabled_step_data(plan)
	step_lookup = {slug: (message, func) for slug, message, func in DEBLOAT_STEPS}
	items = plan.get("items", [])
	ordered = []
	if isinstance(items, list):
		for raw in items:
			if not isinstance(raw, dict):
				continue
			item = install_plan.normalize_item(raw)
			key = item["key"].strip()
			enabled = item["enabled"]
			if key not in step_lookup:
				continue
			ordered.append((key, enabled) + step_lookup[key])
	return ordered


def _validate_execution_step_metadata(plan: dict, execution_steps, args, external_config=None):
	plan["items"] = [
		{"key": slug, "enabled": enabled and not getattr(args, f"skip_{slug.replace('-', '_')}_step", False)}
		for slug, enabled, _, _ in execution_steps
	]
	if external_config is not None:
		if install_plan.is_item_enabled(plan, "debloat-windows-phase-one"):
			config = external_scripts._extract_winutil_config(external_config)
			if config is not None:
				plan["winutil_config"] = config
		if install_plan.is_item_enabled(plan, "debloat-windows-phase-two"):
			arguments = external_scripts._extract_win11debloat_args(external_config)
			if arguments is not None:
				plan["win11debloat_args"] = arguments
	install_plan.validate_enabled_step_data(plan)


def _execution_config_path(args, plan: dict):
	payload = {}
	if install_plan.is_item_enabled(plan, "debloat-windows-phase-one"):
		payload["WinUtil"] = plan["winutil_config"]
	if install_plan.is_item_enabled(plan, "debloat-windows-phase-two"):
		payload["Win11Debloat"] = {"Args": plan["win11debloat_args"].split()}
	if not payload:
		return None, False
	fd, tmp_path = tempfile.mkstemp(prefix="talon_install_plan_runtime_", suffix=".json")
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			json.dump(payload, f, indent=2)
		return tmp_path, True
	except Exception:
		logger.exception("Unable to write runtime configuration %s", tmp_path)
		try:
			os.remove(tmp_path)
		except OSError:
			logger.warning("Unable to remove incomplete runtime configuration %s", tmp_path, exc_info=True)
		raise

def _build_install_ui():
	app = QApplication.instance() or QApplication(sys.argv)
	initialize_error_dialogs()
	app.setQuitOnLastWindowClosed(False)
	base = UIBaseFull()
	for overlay in base.overlays:
		overlay.setWindowOpacity(0.8)
	overlay = base.primary_overlay
	title_label = UITitleText(t("app.install_overlay.title"), parent=overlay)
	UIHeaderText(
		t("app.install_overlay.guidance"),
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
		finished = pyqtSignal(int)
	bus = _SpinnerBus()
	bus.start.connect(spinner.start, Qt.QueuedConnection)
	bus.stop.connect(spinner.stop, Qt.QueuedConnection)
	bus.raiseit.connect(spinner.raise_, Qt.QueuedConnection)
	bus.set_msg.connect(status_label.setText, Qt.QueuedConnection)
	def finish(exit_code):
		spinner.stop()
		if exit_code:
			app.exit(exit_code)
		else:
			QTimer.singleShot(2500, lambda: app.exit(0))
	bus.finished.connect(finish, Qt.QueuedConnection)
	base.show()
	status_label.raise_()
	spinner.raise_()
	return app, status_label, base, spinner, bus

def _update_status(bus, label: UIHeaderText, message: str):
	logger.info("%s", message)
	if label is None:
		return
	bus.set_msg.emit(message)
	bus.raiseit.emit()

def _record_debloat_completion():
	epoch_utc = int(time.time())
	access = winreg.KEY_WRITE
	if hasattr(winreg, "KEY_WOW64_64KEY"):
		access |= winreg.KEY_WOW64_64KEY
	with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, _COMPLETION_REGISTRY_PATH, 0, access) as key:
		winreg.SetValueEx(key, "Version", 0, winreg.REG_SZ, TALON_VERSION)
		winreg.SetValueEx(key, "DebloatRanUtc", 0, winreg.REG_QWORD, epoch_utc)
	logger.info(
		f"Recorded Talon completion marker: HKLM\\{_COMPLETION_REGISTRY_PATH} "
		f"Version={TALON_VERSION}, DebloatRanUtc={epoch_utc}"
	)


def main(argv=None):
	raw_args = sys.argv[1:] if argv is None else list(argv)
	try:
		args = parse_args(argv)
	except (ValueError, SystemExit):
		logger.exception("Invalid command-line arguments")
		raise
	if args.help:
		_show_command_line_help()
		return
	set_headless_mode(args.headless)
	if (
		args.developer_mode
		and not args.headless
		and os.environ.get("TALON_DEV_CONSOLE") != "1"
	):
		if _launch_developer_console(raw_args):
			return
		sys.exit(1)
	if args.headless:
		args.developer_mode = True
	if args.dry_run:
		os.environ["TALON_DRY_RUN"] = "1"
		logger.info("Dry-run mode enabled; execution steps will be previewed without modifying the system.")
	external_config = None
	if args.config:
		config_path = os.path.abspath(args.config)
		if not os.path.isfile(config_path):
			msg = t("errors.config_not_found", {"path": config_path})
			logger.error(msg)
			show_error_popup(msg, allow_continue=False)
			sys.exit(1)
		args.config = config_path
		try:
			external_config = load_json_file(config_path)
			if not isinstance(external_config, (dict, list)):
				raise ValueError("Configuration must be a JSON object or a WinUtil selection list.")
		except Exception as error:
			show_error_popup(t("errors.config_load_failed", {"label": "custom", "error": error}), allow_continue=False)
			return
	plan = {}
	runtime_config_path = args.config
	runtime_config_is_temp = False
	runtime_registry_changes = None
	runtime_selected_browser_package = ""
	runtime_applied_background_path = ""
	execution_steps = [
		(slug, args.step_overrides.get(slug, slug not in step_catalog.OPTIONAL_STEP_SLUGS), message, func)
		for slug, message, func in DEBLOAT_STEPS
	]
	if not args.headless:
		start_requested = bool(run_screen("screen_configuration"))
		if not start_requested:
			logger.info("Initial window closed without Start; exiting before debloat process starts.")
			return
		try:
			plan = install_plan.normalize_imported_plan(_load_install_plan(), args.step_overrides)
			execution_steps = _build_execution_steps_from_plan(plan)
		except Exception as error:
			show_error_popup(t("errors.start_plan_failed", {"error": error}), allow_continue=False)
			return
		if not execution_steps:
			msg = t("errors.empty_execution_plan")
			logger.error(msg)
			show_error_popup(msg, allow_continue=False)
			return
		for raw in plan.get("items", []):
			if isinstance(raw, dict) and str(raw.get("key", "")).strip() == "developer-mode":
				if bool(raw.get("enabled", False)):
					args.developer_mode = True
				break
	else:
		try:
			if isinstance(external_config, dict) and "items" in external_config:
				plan = install_plan.normalize_imported_plan(external_config, args.step_overrides)
				execution_steps = _build_execution_steps_from_plan(plan)
			else:
				args.skip_browser_installation_step = True
				if isinstance(external_config, dict):
					plan = {key: external_config[key] for key in install_plan.metadata_keys() if key in external_config}
		except Exception as error:
			show_error_popup(t("errors.start_plan_failed", {"error": error}), allow_continue=False)
			return
	try:
		_validate_execution_step_metadata(plan, execution_steps, args, external_config)
		if not any(item["enabled"] for item in plan["items"]):
			raise ValueError(t("errors.empty_execution_plan"))
	except Exception as error:
		show_error_popup(t("errors.start_plan_failed", {"error": error}), allow_continue=False)
		return
	runtime_registry_changes = plan.get("registry_changes")
	runtime_selected_browser_package = plan.get("selected_browser_package", "")
	runtime_applied_background_path = plan.get("applied_background_path", "")
	if not args.dry_run:
		if args.headless:
			ensure_admin()
			pre_checks.main()
		try:
			runtime_config_path, runtime_config_is_temp = _execution_config_path(args, plan)
		except Exception as error:
			show_error_popup(t("errors.start_plan_failed", {"error": error}), allow_continue=False)
			return
	def _cleanup_runtime_config():
		if not runtime_config_is_temp or not runtime_config_path:
			return
		try:
			os.remove(runtime_config_path)
		except FileNotFoundError:
			logger.debug("Runtime configuration was already removed: %s", runtime_config_path)
		except Exception as e:
			logger.warning(f"Failed to clean temporary runtime config '{runtime_config_path}': {e}", exc_info=True)
			record_warning()

	app = None
	status_label = None
	spinner = None
	bus = None
	if not args.developer_mode:
		global _INSTALL_UI_BASE
		try:
			app, status_label, _INSTALL_UI_BASE, spinner, bus = _build_install_ui()
		except BaseException:
			_cleanup_runtime_config()
			raise

	def debloat_sequence():
		try:
			if bus is not None:
				bus.start.emit()
				bus.raiseit.emit()
			for slug, enabled, message, func in execution_steps:
				if not enabled:
					logger.info(f"Skipping {slug} step (disabled in install_plan)")
					continue
				if getattr(args, f"skip_{slug.replace('-', '_')}_step", False):
					logger.info(f"Skipping {slug} step")
					continue
				_update_status(bus, status_label, t(message))
				if args.dry_run:
					logger.info(f"Dry-run: would run {slug} step")
					if not args.headless and not args.developer_mode:
						time.sleep(0.8)
					continue
				try:
					if slug in ("debloat-windows-phase-one", "debloat-windows-phase-two"):
						func(runtime_config_path)
					elif slug == "browser-installation":
						func(runtime_selected_browser_package)
					elif slug == "registry-tweaks":
						func(runtime_registry_changes)
					elif slug == "program-installation":
						func(plan.get("chocolatey_packages", []))
					elif slug == "group-policy":
						func(plan.get("group_policy_changes", []))
					elif slug == "apply-background":
						func(runtime_applied_background_path)
					else:
						func()
				except BaseException:
					logger.exception("Debloat step %s failed", slug)
					raise
			if not args.dry_run:
				try:
					_record_debloat_completion()
				except Exception as e:
					logger.exception(f"Failed to record Talon completion marker: {e}")
					show_error_popup(
						t("errors.completion_marker_failed", {"error": e}),
						allow_continue=True,
					)
		finally:
			_cleanup_runtime_config()

	def run_sequence():
		reset_warning_count()
		exit_code = 0
		try:
			with collect_recoverable_errors():
				debloat_sequence()
			warnings = get_warning_count()
			if args.dry_run:
				message = t("app.install_overlay.dry_run_complete")
			elif warnings:
				message = t("app.install_overlay.complete_with_warnings", {"count": warnings})
			else:
				message = t("app.install_overlay.complete_no_restart")
			_update_status(bus, status_label, message)
		except SystemExit as error:
			exit_code = error.code if isinstance(error.code, int) and error.code else 1
			logger.error("Installation stopped with exit code %s", exit_code)
		except BaseException as error:
			exit_code = 1
			logger.exception("Installation failed")
			if bus is not None:
				bus.stop.emit()
			if not args.headless and isinstance(error, Exception):
				try:
					show_error_popup(t("errors.installation_unexpected"), allow_continue=False)
				except SystemExit:
					logger.debug("Installation failure was acknowledged")
				except BaseException:
					logger.exception("Unable to report installation failure")
		finally:
			if bus is not None:
				bus.finished.emit(exit_code)
		if exit_code and bus is None:
			raise SystemExit(exit_code)

	if args.developer_mode or args.headless:
		run_sequence()
	else:
		def start_thread():
			threading.Thread(target=run_sequence, daemon=True).start()
		QTimer.singleShot(0, start_thread)
		sys.exit(app.exec_())

if __name__ == "__main__":
	main()
