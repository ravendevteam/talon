import json
import os
import tempfile

import debloat_components.debloat_registry_tweaks as debloat_registry_tweaks
from debloat_components.debloat_group_policy import normalize_group_policy_changes
from configuration_components import step_catalog
from configuration_components.config_validation import normalize_winutil_config, normalize_win11debloat_args_text
from configuration_components.localization import t
from utilities.util_chocolatey import normalize_chocolatey_packages
from utilities.util_json import load_json_file
from utilities.util_logger import logger
from utilities.util_windows_check import supports_group_policy as group_policy_available


INSTALL_PLAN_VERSION = 1


class InstallPlanError(ValueError):
    pass


def talon_dir() -> str:
    return os.path.join(os.environ.get("TEMP", tempfile.gettempdir()), "talon")


def install_plan_path() -> str:
    return os.path.join(talon_dir(), "install_plan.json")


def metadata_keys() -> tuple:
    return ("winutil_config", "win11debloat_args", "registry_changes", "applied_background_path",
            "chocolatey_packages", "group_policy_changes")


def default_registry_changes():
    return debloat_registry_tweaks.default_registry_changes_payload()


def format_win11debloat_args_for_editor(value) -> str:
    return "\n".join(normalize_win11debloat_args_text(value).split())


def normalize_registry_changes(value):
    return debloat_registry_tweaks.normalize_registry_changes(value)


def _normalize_background_path(value):
    if not isinstance(value, str) or "\0" in value:
        raise ValueError("applied_background_path must be a file path string.")
    return value.strip()


def normalize_metadata_fields(data: dict):
    if not isinstance(data, dict):
        raise ValueError("Install plan must be a JSON object.")
    enabled = {item["key"] for item in _normalize_plan_items(data.get("items", [])) if item["enabled"]}
    fields = (
        ("winutil_config", "debloat-windows-phase-one", normalize_winutil_config, step_catalog.default_winutil_config()),
        ("win11debloat_args", "debloat-windows-phase-two", normalize_win11debloat_args_text, step_catalog.default_win11debloat_args_text()),
        ("registry_changes", "registry-tweaks", normalize_registry_changes, None),
        ("applied_background_path", "apply-background", _normalize_background_path, ""),
        ("chocolatey_packages", "program-installation", normalize_chocolatey_packages, []),
        ("group_policy_changes", "group-policy", normalize_group_policy_changes, []),
    )
    for field, step, normalize, default in fields:
        value = data.get(field, default)
        try:
            value = normalize(value)
            if step in enabled:
                if field == "applied_background_path":
                    if value and not os.path.isfile(value):
                        raise ValueError(f"Background image does not exist: {value}")
                elif not value or (field == "winutil_config" and not value.get("WPFTweaks")):
                    raise ValueError(f"{field} must contain at least one entry for an enabled step.")
        except ValueError as error:
            if step in enabled:
                raise ValueError(f"Invalid data for '{step}': {error}") from error
            logger.debug("Preserving invalid %s data for disabled step %r", field, step, exc_info=True)
        data[field] = value
    if "browser-installation" in enabled:
        package = data.get("selected_browser_package", "")
        data["selected_browser_package"] = normalize_chocolatey_packages([package])[0]
    data["include_browser_install"] = "browser-installation" in enabled


def validate_enabled_step_data(data: dict):
    normalize_metadata_fields(data)
    if is_item_enabled(data, "group-policy") and not group_policy_available():
        raise ValueError(t("configuration.advanced.group_policy_unavailable"))


def step_unavailable_reason(key: str, data: dict, internet_available: bool = True) -> str:
    if key in ("browser-installation", "program-installation") and not internet_available:
        return t("configuration.advanced.internet_required")
    if key == "browser-installation" and not data.get("selected_browser_package"):
        return t("configuration.advanced.browser_required")
    if key == "program-installation" and not data.get("chocolatey_packages"):
        return t("configuration.advanced.program_packages_required")
    if key == "group-policy":
        if not group_policy_available():
            return t("configuration.advanced.group_policy_unavailable")
        if not data.get("group_policy_changes"):
            return t("configuration.advanced.group_policy_changes_required")
    return ""


def apply_step_availability(data: dict, internet_available: bool = True):
    for item in data.get("items", []):
        normalize_item(item)
        if isinstance(item, dict) and step_unavailable_reason(item.get("key", ""), data, internet_available):
            item["enabled"] = False
    data["include_browser_install"] = is_item_enabled(data, "browser-installation")


def copy_metadata_value(value):
    return json.loads(json.dumps(value))


def build_install_plan(
    browser_name: str = "None",
    browser_package: str = "",
    include_browser_install: bool = False,
    preset_key: str = step_catalog.STANDARD_PRESET_KEY,
    internet_available: bool = True,
) -> dict:
    preset = step_catalog.preset_by_key(preset_key)
    preset_plan = copy_metadata_value(preset.get("plan", {}))
    preset_items = {item["key"]: item for item in _normalize_plan_items(preset_plan.get("items"))}
    items = []
    for slug in step_catalog.BOOL_OPTION_SLUGS + step_catalog.STEP_SLUGS:
        raw_item = preset_items.get(slug, {})
        enabled = normalize_item(raw_item)["enabled"] if raw_item else False
        item = {
            "key": slug,
            "text": str(raw_item.get("text", "")),
            "tooltip": str(raw_item.get("tooltip", "")),
            "enabled": enabled,
        }
        if slug == "browser-installation":
            item["enabled"] = bool(include_browser_install and enabled)
        items.append(item)
    winutil_config = copy_metadata_value(preset_plan.get("winutil_config", step_catalog.default_winutil_config()))
    win11debloat_args = copy_metadata_value(preset_plan.get("win11debloat_args", step_catalog.default_win11debloat_args_text()))
    registry_changes = copy_metadata_value(preset_plan.get("registry_changes", None))
    if registry_changes is None:
        registry_changes = default_registry_changes()
    plan = {
        "version": INSTALL_PLAN_VERSION,
        "selected_preset_key": str(preset.get("key", step_catalog.STANDARD_PRESET_KEY)),
        "selected_browser_name": browser_name,
        "selected_browser_package": browser_package,
        "include_browser_install": is_item_enabled({"items": items}, "browser-installation"),
        "items": items,
        "winutil_config": winutil_config,
        "win11debloat_args": win11debloat_args,
        "registry_changes": registry_changes,
        "applied_background_path": preset_plan.get("applied_background_path", ""),
        "chocolatey_packages": copy_metadata_value(preset_plan.get("chocolatey_packages", [])),
        "group_policy_changes": copy_metadata_value(preset_plan.get("group_policy_changes", [])),
    }
    normalize_metadata_fields(plan)
    apply_step_availability(plan, internet_available=internet_available)
    return plan


def normalize_item(item) -> dict:
    if isinstance(item, dict):
        if not isinstance(item.get("key"), str) or not item["key"].strip():
            raise ValueError("Every install plan item must have a nonempty string key.")
        key = item["key"].strip()
        if type(item.get("enabled", False)) is not bool:
            raise ValueError(f"Install plan step '{key}' requires a boolean enabled value.")
        return {
            "key": key,
            "text": str(item.get("text", "")),
            "tooltip": str(item.get("tooltip", "")),
            "enabled": bool(item.get("enabled", False)),
        }
    raise ValueError("Every install plan item must be a JSON object.")


def _normalize_plan_items(items) -> list:
    if not isinstance(items, list):
        raise ValueError("Install plan field 'items' must be a list.")
    known = step_catalog.BOOL_OPTION_SLUGS + step_catalog.STEP_SLUGS
    by_key = {}
    for raw in items:
        item = normalize_item(raw)
        key = item["key"]
        if key in by_key:
            raise ValueError(f"Install plan contains duplicate step '{key}'.")
        if item["enabled"] and key not in known:
            raise ValueError(f"Unknown enabled install plan step: '{key}'.")
        by_key[key] = item
    return [by_key.pop(key, {"key": key, "text": "", "tooltip": "", "enabled": False})
            for key in known] + list(by_key.values())


def normalize_imported_plan(payload: dict, step_overrides: dict = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Install plan must be a JSON object.")
    incoming_version = payload.get("version", INSTALL_PLAN_VERSION)
    if type(incoming_version) is not int:
        raise ValueError("Install plan field 'version' must be an integer.")
    if incoming_version < 1:
        raise ValueError("Install plan field 'version' must be >= 1.")
    if "items" not in payload:
        raise ValueError("Install plan is missing required field: items.")
    if not isinstance(payload.get("items"), list):
        raise ValueError("Install plan field 'items' must be a list.")

    normalized = {
        "version": incoming_version,
        "selected_preset_key": str(payload.get("selected_preset_key", "custom")),
        "selected_browser_name": str(payload.get("selected_browser_name", "None")),
        "selected_browser_package": payload.get("selected_browser_package", ""),
        "items": _normalize_plan_items(payload["items"]),
    }
    if step_overrides:
        for item in normalized["items"]:
            if item["key"] in step_overrides:
                item["enabled"] = step_overrides[item["key"]]
    for key in metadata_keys():
        if key in payload:
            normalized[key] = payload.get(key)
    validate_enabled_step_data(normalized)
    return normalized


def ensure_install_plan_file():
    path = install_plan_path()
    try:
        os.stat(path)
    except FileNotFoundError:
        save_install_plan(build_install_plan())
        return
    load_install_plan()


def reset_install_plan_defaults(internet_available: bool = True):
    save_install_plan(build_install_plan(internet_available=internet_available))


def load_install_plan() -> dict:
    try:
        return normalize_imported_plan(load_json_file(install_plan_path()))
    except Exception as error:
        raise InstallPlanError(f"Unable to load the saved install plan: {error}") from error


def save_install_plan(data: dict):
    normalized = normalize_imported_plan(copy_metadata_value(data))
    path = install_plan_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".install_plan-", suffix=".tmp", delete=False) as output:
            temporary_path = output.name
            json.dump(normalized, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Unable to remove incomplete install plan file: %s", temporary_path, exc_info=True)


def mark_custom(data: dict):
    data["selected_preset_key"] = "custom"


def find_item_index(items: list, key: str) -> int:
    for i, item in enumerate(items):
        if normalize_item(item)["key"] == key:
            return i
    return -1


def set_item_enabled(data: dict, key: str, enabled: bool):
    items = [normalize_item(item) for item in data.get("items", [])]
    for item in items:
        if item["key"] == key:
            item["enabled"] = bool(enabled)
            break
    data["items"] = items
    if key != "browser-installation" or bool(data.get("selected_browser_package", "")):
        mark_custom(data)


def set_item_enabled_for_preset(data: dict, key: str, enabled: bool):
    items = [normalize_item(item) for item in data.get("items", [])]
    for item in items:
        if item["key"] == key:
            item["enabled"] = bool(enabled)
            break
    data["items"] = items


def is_item_enabled(data: dict, key: str) -> bool:
    for item in data.get("items", []):
        n = normalize_item(item)
        if n["key"] == key:
            return bool(n["enabled"])
    return False


def enabled_plan_keys(data: dict) -> list:
    keys = []
    for item in data.get("items", []):
        n = normalize_item(item)
        if not n["key"] or not n["enabled"]:
            continue
        if step_unavailable_reason(n["key"], data):
            continue
        keys.append(n["key"])
    return keys


def visible_enabled_items(data: dict) -> list:
    out = []
    for item in data.get("items", []):
        n = normalize_item(item)
        if not n["enabled"]:
            continue
        if step_unavailable_reason(n["key"], data):
            continue
        if n["key"] in set(step_catalog.BOOL_OPTION_SLUGS + step_catalog.STEP_SLUGS):
            if n["key"] == "browser-installation":
                text = step_catalog.browser_step_text(str(data.get("selected_browser_name", "None")))
                tooltip = step_catalog.browser_tooltip(str(data.get("selected_browser_package", "")))
            else:
                text = step_catalog.step_text(n["key"])
                tooltip = step_catalog.step_tooltip(n["key"])
                if n["key"] == "program-installation":
                    text += ": " + ", ".join(data.get("chocolatey_packages", []))
                elif n["key"] == "group-policy":
                    tooltip += "\n" + "\n".join(
                        f"{row['hive']}\\{row['key_path']}\\{row['name']} = {row['value']!r}"
                        for row in data.get("group_policy_changes", [])
                    )
        else:
            text = n["text"]
            tooltip = n["tooltip"]
        out.append({"key": n["key"], "text": text, "tooltip": tooltip})
    return out


def set_browser(package_id: str, browser_name: str, internet_available: bool = True):
    data = load_install_plan()
    items = [normalize_item(item) for item in data.get("items", [])]
    idx = find_item_index(items, "browser-installation")
    if idx >= 0:
        items[idx]["enabled"] = True
    data["items"] = items
    data["selected_browser_name"] = browser_name
    data["selected_browser_package"] = package_id
    data["include_browser_install"] = True
    apply_step_availability(data, internet_available=internet_available)
    save_install_plan(data)


def skip_browser_install(internet_available: bool = True):
    data = load_install_plan()
    set_item_enabled(data, "browser-installation", False)
    data["selected_browser_name"] = "None"
    data["selected_browser_package"] = ""
    data["include_browser_install"] = False
    apply_step_availability(data, internet_available=internet_available)
    save_install_plan(data)


def apply_internet_availability(available: bool):
    if available:
        return
    data = load_install_plan()
    apply_step_availability(data, internet_available=False)
    save_install_plan(data)


def apply_preset(preset_key: str, internet_available: bool = True):
    current = load_install_plan()
    selected_browser_name = str(current.get("selected_browser_name", "None"))
    selected_browser_package = str(current.get("selected_browser_package", ""))
    preset = step_catalog.preset_by_key(preset_key)
    data = build_install_plan(
        browser_name=selected_browser_name,
        browser_package=selected_browser_package,
        include_browser_install=bool(selected_browser_package),
        preset_key=str(preset.get("key", step_catalog.STANDARD_PRESET_KEY)),
        internet_available=internet_available,
    )
    if not selected_browser_package:
        set_item_enabled_for_preset(data, "browser-installation", False)
        data["selected_preset_key"] = str(preset.get("key", step_catalog.STANDARD_PRESET_KEY))
    save_install_plan(data)
