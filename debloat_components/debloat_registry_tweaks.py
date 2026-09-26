import json
import sys
import winreg
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from utilities.util_modify_registry import set_value
from configuration_components.localization import t


REGISTRY_MODIFICATIONS = [
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
     "TaskbarAl", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
     "AppsUseLightTheme", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
     "SystemUsesLightTheme", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
     "AppCaptureEnabled", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"System\GameConfigStore",
     "GameDVR_Enabled", winreg.REG_DWORD, 0),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
     "AllowGameDVR", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Control Panel\Desktop",
     "MenuShowDelay", winreg.REG_SZ, "0"),
    (winreg.HKEY_CURRENT_USER,
     r"Control Panel\Desktop\WindowMetrics",
     "MinAnimate", winreg.REG_SZ, "0"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
     "ExtendedUIHoverTime", winreg.REG_DWORD, 1),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
     "HideFileExt", winreg.REG_DWORD, 0),
    (winreg.HKEY_CURRENT_USER,
     r"Control Panel\Desktop",
     "DragFullWindows", winreg.REG_SZ, "1"),
]


def default_registry_changes_payload():
    hive_names = {
        winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER",
        winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
    }
    type_names = {
        winreg.REG_DWORD: "REG_DWORD",
        winreg.REG_SZ: "REG_SZ",
    }
    rows = []
    for hive, key_path, name, value_type, value in REGISTRY_MODIFICATIONS:
        rows.append(
            {
                "hive": hive_names.get(hive, str(hive)),
                "key_path": key_path,
                "name": name,
                "value_type": type_names.get(value_type, str(value_type)),
                "value": value,
            }
        )
    return rows


def _parse_hive(value):
    hive_names = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
    }
    if type(value) is int:
        return value if value in hive_names.values() else None
    if isinstance(value, str):
        return hive_names.get(value.strip().upper())
    return None


def _parse_value_type(value):
    type_names = {
        "REG_DWORD": winreg.REG_DWORD,
        "DWORD": winreg.REG_DWORD,
        "REG_SZ": winreg.REG_SZ,
        "SZ": winreg.REG_SZ,
    }
    if type(value) is int:
        return value if value in type_names.values() else None
    if isinstance(value, str):
        return type_names.get(value.strip().upper())
    return None


def normalize_registry_changes(registry_changes):
    if registry_changes is None:
        registry_changes = default_registry_changes_payload()
    if isinstance(registry_changes, str):
        try:
            registry_changes = json.loads(registry_changes)
        except (ValueError, TypeError) as error:
            raise ValueError(f"registry_changes contains invalid JSON: {error}") from error
    if isinstance(registry_changes, dict):
        if set(registry_changes) not in ({"modifications"}, {"items"}):
            raise ValueError("registry_changes must contain only 'modifications' or 'items'.")
        rows = next(iter(registry_changes.values()))
        if not isinstance(rows, list):
            raise ValueError("registry_changes must contain a list in 'modifications' or 'items'.")
    elif isinstance(registry_changes, list):
        rows = registry_changes
    else:
        raise ValueError("registry_changes must be a list or object.")

    required_fields = {"hive", "key_path", "name", "value_type", "value"}
    root_names = {"HKCU", "HKEY_CURRENT_USER", "HKLM", "HKEY_LOCAL_MACHINE",
                  "HKCR", "HKEY_CLASSES_ROOT", "HKU", "HKEY_USERS", "HKCC", "HKEY_CURRENT_CONFIG"}
    out = []
    for idx, raw in enumerate(rows):
        label = f"registry_changes[{idx}]"
        if not isinstance(raw, dict) or set(raw) != required_fields:
            raise ValueError(
                f"{label} must contain exactly hive, key_path, name, value_type, and value."
            )
        hive = _parse_hive(raw["hive"])
        value_type = _parse_value_type(raw["value_type"])
        if hive is None:
            raise ValueError(f"{label}: hive must be HKLM or HKCU.")
        if not isinstance(raw["key_path"], str) or not isinstance(raw["name"], str):
            raise ValueError(f"{label}: key_path and name must be strings.")
        key_path, name = raw["key_path"].strip(), raw["name"].strip()
        segments = key_path.split("\\")
        if (not key_path or len(key_path) > 255 or any(ord(c) < 32 for c in key_path)
                or "/" in key_path or any(part.strip() in ("", ".", "..") for part in segments)
                or segments[0].upper().rstrip(":") in root_names):
            raise ValueError(f"{label}: key_path must be a valid path relative to the selected hive.")
        if not name or len(name) > 16383 or any(ord(c) < 32 for c in name):
            raise ValueError(f"{label}: name must be a nonempty registry value name.")
        value = raw["value"]
        if value_type == winreg.REG_DWORD:
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError(f"{label}: REG_DWORD value must be an integer from 0 to 4294967295.")
        elif value_type == winreg.REG_SZ:
            if not isinstance(value, str) or "\0" in value:
                raise ValueError(f"{label}: REG_SZ value must be a string without null characters.")
        else:
            raise ValueError(f"{label}: value_type must be REG_DWORD or REG_SZ.")
        out.append({
            "hive": "HKEY_CURRENT_USER" if hive == winreg.HKEY_CURRENT_USER else "HKEY_LOCAL_MACHINE",
            "key_path": key_path,
            "name": name,
            "value_type": "REG_DWORD" if value_type == winreg.REG_DWORD else "REG_SZ",
            "value": value,
        })
    return out


def _coerce_registry_modifications(registry_changes):
    rows = normalize_registry_changes(registry_changes)
    if not rows:
        raise ValueError("registry_changes is empty.")
    return [(_parse_hive(row["hive"]), row["key_path"], row["name"],
             _parse_value_type(row["value_type"]), row["value"]) for row in rows]



def main(registry_changes=None):
    try:
        modifications = _coerce_registry_modifications(registry_changes)
    except Exception as e:
        logger.error(f"Invalid registry changes payload: {e}")
        try:
            show_error_popup(
                t("errors.registry_changes_payload_invalid", {"error": e}),
                allow_continue=False
            )
        except Exception:
            logger.exception("Failed to report installation error")
        sys.exit(1)
    failures = 0
    for hive, key_path, name, value_type, value in modifications:
        try:
            logger.info(f"Applying registry tweak: {key_path}\\{name} = {value!r} (type={value_type})")
            set_value(hive, key_path, name, value, value_type)
            logger.info(f"Successfully set {name}")
        except Exception as e:
            logger.error(f"Failed to apply registry tweak {name}: {e}")
            show_error_popup(
                t("errors.registry_tweak_failed", {"target": f"{key_path}\\{name}", "error": e}),
                allow_continue=True
            )
            failures += 1

    if failures:
        logger.warning("Registry tweaks completed with %s failed changes.", failures)
    else:
        logger.info("All registry tweaks applied successfully.")



if __name__ == "__main__":
    main()
