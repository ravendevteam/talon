import json
import os

from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtWidgets import QApplication, QFileDialog

from configuration_components import install_plan, step_catalog
from configuration_components.localization import t
from utilities.util_error_popup import show_error_popup
from utilities.util_json import load_json_file
from utilities.util_logger import logger


class ConfigurationBridge(QObject):
    def __init__(self):
        super().__init__()
        self.start_requested = False
        self.failed = False
        self.internet_available = True
        install_plan.reset_install_plan_defaults()

    def set_internet_available(self, available: bool):
        self.internet_available = bool(available)
        self._apply_availability()

    def _handle_error(self, key: str, error: Exception, fatal: bool = False):
        if self.failed:
            return
        fatal = fatal or isinstance(error, install_plan.InstallPlanError)
        logger.error("Configuration action failed: %s", error, exc_info=(type(error), error, error.__traceback__))
        if fatal:
            self.failed = True
            self.start_requested = False
        try:
            show_error_popup(t(key, {"error": error}), allow_continue=not fatal)
        except SystemExit:
            self.failed = True
            self.start_requested = False
        except Exception:
            logger.exception("Unable to display the configuration error")
            self.failed = True
            self.start_requested = False
        finally:
            if self.failed:
                app = QApplication.instance()
                if app is not None:
                    app.exit(1)

    def _apply_availability(self):
        install_plan.apply_internet_availability(self.internet_available)

    def _save_plan(self, data: dict):
        install_plan.normalize_metadata_fields(data)
        install_plan.apply_step_availability(data, internet_available=self.internet_available)
        install_plan.save_install_plan(data)

    @pyqtSlot(result="QVariantList")
    def getBrowserOptions(self):
        if self.failed:
            return []
        try:
            return step_catalog.browser_options()
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return []

    @pyqtSlot(result="QVariantList")
    def getInstallPlanItems(self):
        if self.failed:
            return []
        try:
            return install_plan.visible_enabled_items(install_plan.load_install_plan())
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return []

    @pyqtSlot(result="QVariantList")
    def getPresetOptions(self):
        if self.failed:
            return []
        try:
            return step_catalog.preset_options()
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return []

    @pyqtSlot(result=str)
    def getSelectedPresetKey(self):
        if self.failed:
            return ""
        try:
            data = install_plan.load_install_plan()
            return str(data.get("selected_preset_key", step_catalog.STANDARD_PRESET_KEY))
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return ""

    @pyqtSlot(result="QVariantMap")
    def getExecutionPlan(self):
        if self.failed:
            return {}
        try:
            data = install_plan.load_install_plan()
            return {
                "version": int(data.get("version", install_plan.INSTALL_PLAN_VERSION)),
                "enabled_keys": install_plan.enabled_plan_keys(data),
                "metadata": {
                    "selected_browser_package": str(data.get("selected_browser_package", "")),
                    "selected_browser_name": str(data.get("selected_browser_name", "None")),
                    "winutil_config": data.get("winutil_config", step_catalog.default_winutil_config()),
                    "win11debloat_args": str(data.get("win11debloat_args", step_catalog.default_win11debloat_args_text())),
                    "registry_changes": data.get("registry_changes", install_plan.default_registry_changes()),
                    "chocolatey_packages": data.get("chocolatey_packages", []),
                    "group_policy_changes": data.get("group_policy_changes", []),
                    "applied_background_path": str(data.get("applied_background_path", "")),
                },
            }
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return {}

    @pyqtSlot(result="QVariantList")
    def getAdvancedArgs(self):
        if self.failed:
            return []
        try:
            data = install_plan.load_install_plan()
            items = [install_plan.normalize_item(item) for item in data.get("items", [])]
            out = []
            known_keys = set(step_catalog.BOOL_OPTION_SLUGS + step_catalog.STEP_SLUGS)
            for it in items:
                label = it["text"]
                if it["key"] in known_keys:
                    if it["key"] == "browser-installation":
                        if str(data.get("selected_browser_package", "")).strip():
                            label = step_catalog.browser_step_text(str(data.get("selected_browser_name", "None")))
                        else:
                            label = step_catalog.step_text(it["key"])
                    else:
                        label = step_catalog.step_text(it["key"])
                reason = install_plan.step_unavailable_reason(
                    it["key"], data, internet_available=self.internet_available
                )
                out.append({
                    "key": it["key"],
                    "label": label,
                    "value": bool(it["enabled"]) and not reason,
                    "available": not bool(reason),
                    "unavailableReason": reason,
                })
            return out
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return []

    @pyqtSlot(str)
    def toggleAdvancedArg(self, key: str):
        if self.failed:
            return
        try:
            data = install_plan.load_install_plan()
            items = [install_plan.normalize_item(item) for item in data.get("items", [])]
            for item in items:
                if item["key"] == key:
                    reason = install_plan.step_unavailable_reason(
                        key, data, internet_available=self.internet_available
                    )
                    if not item["enabled"] and reason:
                        raise ValueError(reason)
                    item["enabled"] = not bool(item["enabled"])
                    break
            data["selected_preset_key"] = "custom"
            if not data.get("selected_browser_package", ""):
                for item in items:
                    if item["key"] == "browser-installation":
                        item["enabled"] = False
                        break
            data["items"] = items
            data["include_browser_install"] = any(
                item["key"] == "browser-installation" and bool(item["enabled"]) for item in items
            )
            self._save_plan(data)
        except Exception as e:
            self._handle_error("errors.update_plan_failed", e)

    @pyqtSlot(int)
    def removeInstallPlanItem(self, index: int):
        if self.failed:
            return
        try:
            data = install_plan.load_install_plan()
            items = [install_plan.normalize_item(item) for item in data.get("items", [])]
            enabled_items = []
            for item in items:
                if item["enabled"]:
                    if item["key"] == "browser-installation" and not data.get("selected_browser_package", ""):
                        continue
                    enabled_items.append(item)
            if 0 <= index < len(enabled_items):
                remove_key = enabled_items[index]["key"]
                for item in items:
                    if item["key"] == remove_key:
                        item["enabled"] = False
                        break
                data["selected_preset_key"] = "custom"
            data["items"] = items
            data["include_browser_install"] = any(
                item["key"] == "browser-installation" and bool(item["enabled"]) for item in items
            )
            self._save_plan(data)
        except Exception as e:
            self._handle_error("errors.update_plan_failed", e)

    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def selectBrowser(self, package_id: str, browser_name: str = "Unknown"):
        if self.failed:
            return
        try:
            install_plan.set_browser(package_id, browser_name, internet_available=self.internet_available)
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error)

    @pyqtSlot()
    def skipBrowserInstall(self):
        if self.failed:
            return
        try:
            install_plan.skip_browser_install(internet_available=self.internet_available)
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error)

    @pyqtSlot()
    def resetInstallPlanDefaults(self):
        if self.failed:
            return
        try:
            install_plan.reset_install_plan_defaults(internet_available=self.internet_available)
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error)

    @pyqtSlot(str)
    def selectPreset(self, preset_key: str):
        if self.failed:
            return
        try:
            install_plan.apply_preset(preset_key, internet_available=self.internet_available)
        except Exception as e:
            self._handle_error("errors.update_plan_failed", e)

    @pyqtSlot()
    def importInstallPlan(self):
        if self.failed:
            return
        try:
            path, _ = QFileDialog.getOpenFileName(None, t("configuration.dialogs.import_plan_title"), "", t("configuration.dialogs.json_files_filter"))
            if not path:
                return
            payload = load_json_file(path)
            data = install_plan.normalize_imported_plan(payload)
            install_plan.mark_custom(data)
            self._save_plan(data)
        except Exception as e:
            self._handle_error("errors.import_plan_failed", e)

    @pyqtSlot()
    def importWinUtilConfig(self):
        if self.failed:
            return
        try:
            path, _ = QFileDialog.getOpenFileName(None, t("configuration.dialogs.import_winutil_title"), "", t("configuration.dialogs.json_files_filter"))
            if not path:
                return
            payload = load_json_file(path)
            if not isinstance(payload, (dict, list)):
                raise ValueError(t("errors.winutil_config_invalid"))
            data = install_plan.load_install_plan()
            data["winutil_config"] = install_plan.normalize_winutil_config(payload)
            install_plan.mark_custom(data)
            self._save_plan(data)
        except Exception as e:
            self._handle_error("errors.import_winutil_failed", e)

    @pyqtSlot()
    def exportInstallPlan(self):
        if self.failed:
            return
        try:
            data = install_plan.load_install_plan()
            path, _ = QFileDialog.getSaveFileName(None, t("configuration.dialogs.export_plan_title"), "install_plan.json", t("configuration.dialogs.json_files_filter"))
            if not path:
                return
            if not path.lower().endswith(".json"):
                path = f"{path}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self._handle_error("errors.export_plan_failed", e)

    @pyqtSlot()
    def setAppliedBackground(self):
        if self.failed:
            return
        try:
            path, _ = QFileDialog.getOpenFileName(
                None,
                t("configuration.dialogs.set_background_title"),
                "",
                t("configuration.dialogs.image_files_filter"),
            )
            if not path:
                return
            if not os.path.isfile(path):
                raise ValueError(t("errors.background_file_missing"))
            data = install_plan.load_install_plan()
            data["applied_background_path"] = os.path.abspath(path)
            install_plan.mark_custom(data)
            self._save_plan(data)
        except Exception as e:
            self._handle_error("errors.set_background_failed", e)

    @pyqtSlot()
    def startDebloat(self):
        if self.failed:
            return
        self.start_requested = False
        try:
            data = install_plan.load_install_plan()
            install_plan.validate_enabled_step_data(data)
            self._apply_availability()
        except Exception as e:
            self._handle_error("errors.start_plan_failed", e)
            return
        self.start_requested = True
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @pyqtSlot(result=str)
    def getWin11DebloatArgsText(self):
        if self.failed:
            return ""
        try:
            data = install_plan.load_install_plan()
            return install_plan.format_win11debloat_args_for_editor(data.get("win11debloat_args", ""))
        except Exception as error:
            self._handle_error("errors.save_win11_args_failed", error, fatal=True)
            return ""

    @pyqtSlot(str, result=bool)
    def saveWin11DebloatArgsText(self, text: str):
        if self.failed:
            return False
        try:
            data = install_plan.load_install_plan()
            data["win11debloat_args"] = install_plan.normalize_win11debloat_args_text(text)
            install_plan.mark_custom(data)
            self._save_plan(data)
            return True
        except Exception as e:
            self._handle_error("errors.save_win11_args_failed", e)
            return False

    @pyqtSlot(result=str)
    def getRegistryChangesText(self):
        if self.failed:
            return ""
        try:
            data = install_plan.load_install_plan()
            value = data.get("registry_changes", None)
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            return json.dumps(value, indent=2)
        except Exception as error:
            self._handle_error("errors.save_registry_changes_failed", error, fatal=True)
            return ""

    @pyqtSlot(str, result=bool)
    def saveRegistryChangesText(self, text: str):
        if self.failed:
            return False
        try:
            raw = str(text).strip()
            parsed = json.loads(raw)
            changes = install_plan.normalize_registry_changes(parsed)
            data = install_plan.load_install_plan()
            data["registry_changes"] = changes
            install_plan.mark_custom(data)
            self._save_plan(data)
            return True
        except Exception as e:
            self._handle_error("errors.save_registry_changes_failed", e)
            return False

    @pyqtSlot(result=bool)
    def isGroupPolicyAvailable(self):
        if self.failed:
            return False
        try:
            return install_plan.group_policy_available()
        except Exception as error:
            self._handle_error("errors.update_plan_failed", error, fatal=True)
            return False

    @pyqtSlot(result=str)
    def getChocolateyPackagesText(self):
        if self.failed:
            return ""
        try:
            data = install_plan.load_install_plan()
            return "\n".join(install_plan.normalize_chocolatey_packages(data.get("chocolatey_packages", [])))
        except Exception as error:
            self._handle_error("errors.save_program_packages_failed", error, fatal=True)
            return ""

    @pyqtSlot(str, result=bool)
    def saveChocolateyPackagesText(self, text: str):
        if self.failed:
            return False
        try:
            packages = install_plan.normalize_chocolatey_packages(
                [line.strip() for line in str(text).splitlines() if line.strip()]
            )
            data = install_plan.load_install_plan()
            data["chocolatey_packages"] = packages
            if not packages:
                install_plan.set_item_enabled_for_preset(data, "program-installation", False)
            install_plan.mark_custom(data)
            self._save_plan(data)
            return True
        except Exception as e:
            self._handle_error("errors.save_program_packages_failed", e)
            return False

    @pyqtSlot(result=str)
    def getGroupPolicyChangesText(self):
        if self.failed:
            return "[]"
        try:
            data = install_plan.load_install_plan()
            return json.dumps(data.get("group_policy_changes", []), indent=2)
        except Exception as error:
            self._handle_error("errors.save_group_policy_changes_failed", error, fatal=True)
            return "[]"

    @pyqtSlot(str, result=bool)
    def saveGroupPolicyChangesText(self, text: str):
        if self.failed:
            return False
        try:
            if not install_plan.group_policy_available():
                raise ValueError(t("errors.group_policy_unsupported"))
            raw = str(text).strip()
            changes = install_plan.normalize_group_policy_changes(json.loads(raw) if raw else [])
            data = install_plan.load_install_plan()
            data["group_policy_changes"] = changes
            if not changes:
                install_plan.set_item_enabled_for_preset(data, "group-policy", False)
            install_plan.mark_custom(data)
            self._save_plan(data)
            return True
        except Exception as e:
            self._handle_error("errors.save_group_policy_changes_failed", e)
            return False
