import os
import sys
import re
import json
import ssl
import tempfile
import urllib.request
import urllib.parse
from utilities.util_logger import logger
from utilities.util_powershell_handler import run_powershell_command
from utilities.util_error_popup import show_error_popup

def _is_url(value: str) -> bool:
    try:
        p = urllib.parse.urlparse(value)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def _download_config(url: str) -> str:
    logger.info(f"Downloading Config from: {url}")
    ctx = None
    if url.lower().startswith("https"):
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": "Talon/1.0"})
    with urllib.request.urlopen(request, timeout=30, context=ctx) as resp:
        data = resp.read()
    try:
        json.loads(data.decode("utf-8-sig"))
    except Exception as e:
        raise RuntimeError(f"Downloaded config is not valid JSON: {e}")
    fd, tmp_path = tempfile.mkstemp(prefix="talon_config_", suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    logger.info(f"Saved downloaded config to: {tmp_path}")
    return tmp_path

def main(config_path=None):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        components_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(components_dir)

    if config_path and isinstance(config_path, str) and _is_url(config_path):
        try:
            config_path = _download_config(config_path)
        except Exception as e:
            logger.error(f"Failed to download config: {e}")
            return 
            
    if not config_path:
        config_path = os.path.join(base_path, 'configs', 'default.json')

    if not os.path.exists(config_path):
        logger.error(f"Config not found: {config_path}")
        return

    logger.info(f"Using Config: {config_path}")

    winutil_args_path = config_path 
    win11debloat_args = [] 

    default_w11_config = os.path.join(base_path, 'configs', 'win11debloat_default.json')
    if os.path.exists(default_w11_config):
        try:
            with open(default_w11_config, 'r') as f:
                win11debloat_args = json.load(f)
        except Exception:
            logger.warning("Failed to load default Win11Debloat config.")

    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            user_data = json.load(f)
        
        if isinstance(user_data, dict) and ("winutil" in user_data or "win11debloat" in user_data):
            logger.info("Detected Unified Config format.")
            
            if "winutil" in user_data:
                fd, temp_winutil_path = tempfile.mkstemp(prefix="talon_winutil_extracted_", suffix=".json")
                with os.fdopen(fd, "w") as tmp:
                    json.dump(user_data["winutil"], tmp, indent=4)
                winutil_args_path = temp_winutil_path
                logger.info(f"Extracted WinUtil config to: {winutil_args_path}")
            
            if "win11debloat" in user_data:
                if isinstance(user_data["win11debloat"], list):
                    win11debloat_args = user_data["win11debloat"]
                    logger.info("Loaded custom Win11Debloat arguments.")
    except Exception as e:
        logger.warning(f"Error parsing config file ({e}). Treating as legacy WinUtil config.")

    winutil_script = os.path.join(base_path, 'external_scripts', 'winutil.ps1')
    if os.path.exists(winutil_script):
        cmd1 = f"& '{winutil_script}' -Config '{winutil_args_path}' -Run -NoUI"
        logger.info("Executing ChrisTitusTech WinUtil")
        try:
            run_powershell_command(cmd1, monitor_output=True, termination_str='Tweaks are Finished')
        except Exception as e:
            logger.error(f"WinUtil execution failed: {e}")

    win11debloat_script = os.path.join(base_path, 'external_scripts', 'Raphire-Win11Debloat-c523386', 'Win11Debloat.ps1')
    if os.path.exists(win11debloat_script):
        flags = ' '.join(win11debloat_args)
        cmd2 = f"& '{win11debloat_script}' {flags}"
        logger.info(f"Executing Raphi Win11Debloat with flags: {flags}")
        try:
            run_powershell_command(cmd2)
        except Exception as e:
            logger.error(f"Win11Debloat execution failed: {e}")
            
    logger.info("External scripts sequence complete.")

if __name__ == "__main__":
    main()