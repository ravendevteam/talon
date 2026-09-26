import os
import sys
import json
import ssl
import tempfile
import glob
import re
import shlex
import urllib.request
import urllib.parse
from configuration_components import step_catalog
from configuration_components.config_validation import (
    normalize_win11debloat_args_text,
    normalize_winutil_config,
    validate_winutil_selections,
)
from configuration_components.localization import t
from utilities.util_json import load_json_file
from utilities.util_logger import logger
from utilities.util_powershell_handler import run_powershell_command
from utilities.util_error_popup import record_warning, show_error_popup


def _split_arguments(value):
    if isinstance(value, list):
        normalize_win11debloat_args_text(value)
        return list(value)
    lexer = shlex.shlex(normalize_win11debloat_args_text(value), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    return list(lexer)


def _powershell_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _script_command(path, arguments):
    tokens = []
    for argument in arguments:
        if re.fullmatch(r"-[A-Za-z][A-Za-z0-9]*(?::\$(?:true|false))?", argument, re.IGNORECASE):
            tokens.append(argument)
        else:
            tokens.append(_powershell_literal(argument))
    invocation = "& " + _powershell_literal(path) + " " + " ".join(tokens)
    return (
        "$LASTEXITCODE = 0; try { " + invocation
        + "; if (-not $?) { if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; exit 1 }; exit 0 } "
        "catch { Write-Error -ErrorRecord $_ -ErrorAction Continue; exit 1 }"
    )


def _is_url(value: str) -> bool:
    try:
        p = urllib.parse.urlparse(value)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        logger.debug("Unable to parse config location as a URL: %r", value, exc_info=True)
        return False


def _download_config(url: str) -> str:
    logger.info(f"Downloading config from: {url}")
    ctx = None
    if url.lower().startswith("https"):
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            logger.warning("Unable to load bundled CA certificates; using system certificates", exc_info=True)
            ctx = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": "Talon/1.0"})
    with urllib.request.urlopen(request, timeout=30, context=ctx) as resp:
        data = resp.read()
    try:
        json.loads(data)
    except Exception as e:
        raise RuntimeError(t("errors.downloaded_config_invalid", {"error": e}))
    fd, tmp_path = tempfile.mkstemp(prefix="talon_config_", suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    logger.info(f"Saved downloaded config to: {tmp_path}")
    return tmp_path


def _load_json_config(path: str, label: str):
    try:
        return load_json_file(path)
    except Exception as e:
        logger.error(f"Failed to load {label} config: {e}")
        try:
            show_error_popup(
                t("errors.config_load_failed", {"label": label, "error": e}),
                allow_continue=False,
            )
        except Exception:
            logger.exception("Failed to report installation error")
        sys.exit(1)


def _write_temp_config(data, prefix: str) -> str:
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    logger.info(f"Saved generated config to: {tmp_path}")
    return tmp_path


def _normalize_winutil_tweaks(value):
    return normalize_winutil_config(value)["WPFTweaks"]


def _extract_winutil_config(data):
    if isinstance(data, list):
        return _normalize_winutil_tweaks(data)
    if not isinstance(data, dict):
        raise ValueError("External configuration must be an object or a WinUtil selection list.")
    if any(key in data for key in ("winutil_config", "WinUtil", "payload")):
        return _normalize_winutil_tweaks(data)
    if any(key in data for key in ("WPFTweaks", "WPFInstall", "WPFFeature", "WPFAppx", "WPFToggle", "Install")):
        selections = {key: value for key, value in data.items()
                      if key not in ("win11debloat_args", "Win11Debloat")}
        return _normalize_winutil_tweaks(selections)
    return None


def _extract_win11debloat_args(data):
    if not isinstance(data, dict):
        if isinstance(data, list):
            return None
        raise ValueError("External configuration must be an object or a WinUtil selection list.")
    if "win11debloat_args" in data:
        return _split_arguments(data["win11debloat_args"])
    if "Win11Debloat" not in data:
        return None
    win11 = data["Win11Debloat"]
    if isinstance(win11, dict):
        if len(win11) != 1 or not set(win11).issubset({"Args", "args"}):
            raise ValueError("Win11Debloat configuration supports only one Args or args field.")
        if "Args" in win11:
            args = win11["Args"]
        elif "args" in win11:
            args = win11["args"]
        else:
            raise ValueError("Win11Debloat configuration must contain Args or args.")
    else:
        args = win11
    return _split_arguments(args)


def _prepare_context(config_path=None):
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        components_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(components_dir)

    if config_path and isinstance(config_path, str) and _is_url(config_path):
        try:
            config_path = _download_config(config_path)
        except Exception as e:
            logger.error(f"Failed to download config: {e}")
            try:
                show_error_popup(
                    t("errors.config_download_failed", {"error": e}),
                    allow_continue=False,
                )
            except Exception:
                logger.exception("Failed to report installation error")
            sys.exit(1)

    user_config = None
    if config_path:
        if not os.path.exists(config_path):
            logger.error(f"Config not found: {config_path}")
            try:
                show_error_popup(
                    t("errors.config_missing", {"path": config_path}),
                    allow_continue=False,
                )
            except Exception:
                logger.exception("Failed to report installation error")
            sys.exit(1)
        user_config = _load_json_config(config_path, "custom")
        if not isinstance(user_config, (dict, list)):
            raise ValueError("External configuration must be an object or a WinUtil selection list.")
        logger.info(f"Using custom config: {config_path}")
    else:
        logger.info("Using embedded defaults from install_plan/runtime.")

    return base_path, user_config


def run_winutil(config_path=None):
    base_path, user_config = _prepare_context(config_path)

    winutil_config = None
    if user_config is not None:
        winutil_config = _extract_winutil_config(user_config)
        if winutil_config is None:
            logger.info("Custom config has no WinUtil config; using embedded default WinUtil config.")
    if winutil_config is None:
        winutil_config = step_catalog.default_winutil_tweaks()

    winutil_path = os.path.join(base_path, "external_scripts", "winutil.ps1")
    if not os.path.exists(winutil_path):
        logger.error(f"Bundled WinUtil script not found: {winutil_path}")
        try:
            show_error_popup(
                t("errors.bundled_winutil_missing", {"path": winutil_path}),
                allow_continue=False,
            )
        except Exception:
            logger.exception("Failed to report installation error")
        sys.exit(1)

    logger.info("Executing ChrisTitusTech WinUtil")
    winutil_config = validate_winutil_selections(winutil_path, winutil_config)
    winutil_config_path = _write_temp_config(winutil_config, "talon_winutil_")
    logger.info(f"Using WinUtil config: {winutil_config_path}")
    try:
        run_powershell_command(_script_command(winutil_path, ["-Config", winutil_config_path]))
    except Exception as e:
        logger.exception("Failed to execute ChrisTitusTech WinUtil")
        show_error_popup(t("errors.winutil_failed", {"error": e}), allow_continue=True)
        logger.warning("Continuing after incomplete ChrisTitusTech WinUtil execution")
        return False
    finally:
        try:
            os.remove(winutil_config_path)
        except FileNotFoundError:
            logger.debug("WinUtil temporary configuration was already removed: %s", winutil_config_path)
        except Exception:
            logger.warning("Unable to remove WinUtil temporary configuration %s", winutil_config_path, exc_info=True)
            record_warning()
    logger.info("Successfully executed ChrisTitusTech WinUtil")
    return True


def run_win11debloat(config_path=None):
    base_path, user_config = _prepare_context(config_path)

    win11debloat_args = None
    if user_config is not None:
        win11debloat_args = _extract_win11debloat_args(user_config)
        if win11debloat_args is None:
            logger.info("Custom config has no Win11Debloat args; using embedded default Win11Debloat args.")
    if win11debloat_args is None:
        win11debloat_args = step_catalog.default_win11debloat_args()

    win11debloat_path = ""
    candidates = sorted(
        glob.glob(os.path.join(base_path, "external_scripts", "Raphire-Win11Debloat-*", "Win11Debloat.ps1"))
    )
    if len(candidates) > 1:
        raise ValueError("Expected exactly one Win11Debloat bundle in external_scripts.")
    if candidates:
        win11debloat_path = candidates[-1]
    if not os.path.exists(win11debloat_path):
        logger.error(f"Bundled Win11Debloat script not found: {win11debloat_path}")
        try:
            show_error_popup(
                t("errors.bundled_win11debloat_missing", {"path": win11debloat_path}),
                allow_continue=False,
            )
        except Exception:
            logger.exception("Failed to report installation error")
        sys.exit(1)

    logger.info("Executing Raphi Win11Debloat")
    if not win11debloat_args:
        raise ValueError("Win11Debloat requires at least one argument for an enabled step.")
    try:
        run_powershell_command(_script_command(win11debloat_path, win11debloat_args))
    except Exception as e:
        logger.exception("Failed to execute Raphi Win11Debloat")
        show_error_popup(t("errors.win11debloat_failed", {"error": e}), allow_continue=True)
        logger.warning("Continuing after incomplete Raphi Win11Debloat execution")
        return False
    logger.info("Successfully executed Raphi Win11Debloat")
    return True


def main(config_path=None):
    winutil_complete = run_winutil(config_path)
    win11debloat_complete = run_win11debloat(config_path)
    if winutil_complete and win11debloat_complete:
        logger.info("All external debloat scripts executed successfully.")
    else:
        logger.warning("External debloat scripts finished with warnings.")


if __name__ == "__main__":
    main()
