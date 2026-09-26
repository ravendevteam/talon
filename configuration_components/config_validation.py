import json
from pathlib import Path
import re


_WINUTIL_GROUPS = ("WPFTweaks", "WPFInstall", "WPFFeature", "WPFAppx")


def normalize_winutil_config(value) -> dict:
    while isinstance(value, dict):
        wrappers = [key for key in ("winutil_config", "WinUtil", "payload") if key in value]
        if not wrappers:
            break
        if len(wrappers) != 1:
            raise ValueError("WinUtil configuration contains multiple selection wrappers.")
        value = value[wrappers[0]]

    if isinstance(value, list):
        value = {"WPFTweaks": value}
    if not isinstance(value, dict) or not value:
        raise ValueError("WinUtil configuration must contain a selection list.")
    unsupported = sorted(set(value) - set(_WINUTIL_GROUPS))
    if unsupported:
        raise ValueError("Unsupported WinUtil configuration fields: " + ", ".join(unsupported))

    tweaks = []
    for group, entries in value.items():
        if not isinstance(entries, list):
            raise ValueError(f"WinUtil {group} must be a list of nonempty strings.")
        for index, item in enumerate(entries, start=1):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"WinUtil {group} entry {index} must be a nonempty string.")
            name = item.strip()
            if any(character.isspace() or ord(character) < 32 for character in name):
                raise ValueError(f"WinUtil {group} entry {index} contains invalid whitespace or control characters.")
            if name.startswith("WPFToggle"):
                raise ValueError(f"WinUtil cannot apply toggle selection '{name}' in unattended config mode.")
            if name not in tweaks:
                tweaks.append(name)

    return {"WPFTweaks": tweaks}


def validate_winutil_selections(script_path, selections) -> list:
    selections = normalize_winutil_config(selections)["WPFTweaks"]
    if not selections:
        raise ValueError("WinUtil requires at least one selection for an enabled step.")
    source = Path(script_path).read_text(encoding="utf-8-sig")
    known = set()
    for catalog, prefix in (("tweaks", "WPFTweaks"), ("applications", "WPFInstall"),
                            ("feature", "WPFFeature"), ("appx", "WPFAppx")):
        matches = re.findall(
            rf"(?ms)^\$sync\.configs\.{catalog}\s*=\s*@'\r?\n(.*?)^'@", source,
        )
        if len(matches) != 1:
            raise ValueError(f"Bundled WinUtil has an unsupported {catalog} catalog format.")
        try:
            entries = json.loads(matches[0])
        except json.JSONDecodeError as error:
            raise ValueError(f"Bundled WinUtil has an invalid {catalog} catalog.") from error
        if not isinstance(entries, dict):
            raise ValueError(f"Bundled WinUtil {catalog} catalog must be an object.")
        known.update(key for key in entries if key.startswith(prefix))
    unsupported = [key for key in selections if key not in known]
    if unsupported:
        raise ValueError("Selections unsupported by bundled WinUtil: " + ", ".join(unsupported))
    return selections


def normalize_win11debloat_args_text(value) -> str:
    if isinstance(value, list):
        for index, argument in enumerate(value, start=1):
            if not isinstance(argument, str):
                raise ValueError(f"Win11Debloat argument {index} must be a string.")
        value = " ".join(value)
    if not isinstance(value, str):
        raise ValueError("Win11Debloat arguments must be a string or a list of strings.")
    if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
        raise ValueError("Win11Debloat arguments contain invalid control characters.")
    return re.sub(r"\s+", " ", value.strip())
