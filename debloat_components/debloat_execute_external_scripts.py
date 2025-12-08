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
	logger.info(f"Downloading WinUtil config from: {url}")
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
	fd, tmp_path = tempfile.mkstemp(prefix="talon_winutil_", suffix=".json")
	with os.fdopen(fd, "wb") as f:
		f.write(data)
	logger.info(f"Saved downloaded config to: {tmp_path}")
	return tmp_path



def main(config_path=None, win11debloat_config_path=None):
	if getattr(sys, 'frozen', False):
		base_path = os.path.dirname(sys.executable)
	else:
		components_dir = os.path.dirname(os.path.abspath(__file__))
		base_path = os.path.dirname(components_dir)
	if config_path and isinstance(config_path, str) and _is_url(config_path):
		try:
			config_path = _download_config(config_path)
		except Exception as e:
			logger.error(f"Failed to download WinUtil config: {e}")
			try:
				show_error_popup(
					f"Failed to download WinUtil config from URL.\n{e}",
					allow_continue=False,
				)
			except Exception:
				pass
			sys.exit(1)
	if not config_path:
		config_path = os.path.join(base_path, 'configs', 'default.json')
	if not os.path.exists(config_path):
		logger.error(f"WinUtil config not found: {config_path}")
		try:
			show_error_popup(
				f"WinUtil config not found:\n{config_path}",
				allow_continue=False,
			)
		except Exception:
			pass
		sys.exit(1)
	logger.info(f"Using WinUtil config: {config_path}")
	winutil_path = os.path.join(base_path, 'external_scripts', 'winutil.ps1')
	if not os.path.exists(winutil_path):
		logger.error(f"Bundled WinUtil script not found: {winutil_path}")
		try:
			show_error_popup(
				f"Bundled WinUtil script not found:\n{winutil_path}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)
	cmd1 = f"& '{winutil_path}' -Config '{config_path}' -Run -NoUI"
	logger.info("Executing ChrisTitusTech WinUtil")
	try:
		run_powershell_command(
			cmd1,
			monitor_output=True,
			termination_str='Tweaks are Finished',
		)
		logger.info("Successfully executed ChrisTitusTech WinUtil")
	except Exception as e:
		logger.error(f"Failed to execute ChrisTitusTech WinUtil: {e}")
		try:
			show_error_popup(
				f"Failed to execute ChrisTitusTech WinUtil:\n{e}",
				allow_continue=False,
			)
		except Exception:
			pass
		sys.exit(1)
	win11debloat_path = os.path.join(base_path, 'external_scripts', 'Raphire-Win11Debloat-c523386', 'Win11Debloat.ps1')
	if not os.path.exists(win11debloat_path):
		logger.error(f"Bundled Win11Debloat script not found: {win11debloat_path}")
		try:
			show_error_popup(
				f"Bundled Win11Debloat script not found:\n{win11debloat_path}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)

	if not win11debloat_config_path:
		win11debloat_config_path = os.path.join(base_path, 'configs', 'win11debloat_default.json')

	if not os.path.exists(win11debloat_config_path):
		logger.error(f"Win11Debloat config not found: {win11debloat_config_path}")
		try:
			show_error_popup(
				f"Win11Debloat config not found:\n{win11debloat_config_path}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)

	try:
		with open(win11debloat_config_path, 'r') as f:
			args2 = json.load(f)
		if not isinstance(args2, list):
			raise ValueError("Config JSON must contain a list of arguments.")
	except Exception as e:
		logger.error(f"Failed to load Win11Debloat config: {e}")
		try:
			show_error_popup(
				f"Failed to load Win11Debloat config:\n{e}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)

	flags = ' '.join(args2)
	cmd2 = f"& '{win11debloat_path}' {flags}"
	logger.info("Executing Raphi Win11Debloat")
	try:
		run_powershell_command(cmd2)
		logger.info("Successfully executed Raphi Win11Debloat")
	except Exception as e:
		logger.error(f"Failed to execute Raphi Win11Debloat: {e}")
		try:
			show_error_popup(
				f"Failed to execute Raphi Win11Debloat:\n{e}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)

	logger.info("All external debloat scripts executed successfully.")



if __name__ == "__main__":
	main()