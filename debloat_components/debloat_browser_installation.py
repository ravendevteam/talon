import os
import sys
import json
import tempfile
import subprocess
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from utilities.util_powershell_handler import run_powershell_command



def load_choice() -> str:
	temp_dir = os.environ.get('TEMP', tempfile.gettempdir())
	choice_file = os.path.join(temp_dir, 'talon', 'browser_choice.json')
	if not os.path.exists(choice_file):
		raise FileNotFoundError(f"Browser choice file not found: {choice_file}")
	with open(choice_file, 'r') as f:
		data = json.load(f)
	browser = data.get('browser')
	if not browser:
		raise ValueError(f"No 'browser' key in {choice_file}")
	return browser



def _get_link_and_flags(item: str) -> tuple | None:
	# this and `_install_from_src` were created by me because choco was not installing chrome (from what i have heard)
	# and this also limits install requirements for talon. 2 ravens 30 lines of code.
    match item:
        case "googlechrome":
            return "https://dl.google.com/tag/s/appguid%3D%7B8A69D345-D564-463C-AFF1-A69D9E530F96%7D%26iid%3D%7BAF2217C4-176B-12DB-546A-461311F7E448%7D%26lang%3Den%26browser%3D3%26usagestats%3D0%26appname%3DGoogle%2520Chrome%26needsadmin%3Dprefers%26ap%3D-arch_x64-statsdef_1%26installdataindex%3Dempty/update2/installers/ChromeSetup.exe", "/silent /install"
        case "waterfox":
            return "https://cdn1.waterfox.net/waterfox/releases/6.6.4/WINNT_x86_64/Waterfox%20Setup%206.6.4.exe", "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES"
        case "brave":
            return "https://referrals.brave.com/latest/BraveBrowserSetup.exe", "/silent /install"
        case "firefox":
            return "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US", "/S"
        case "librewolf":
            return "https://gitlab.com/api/v4/projects/44042130/packages/generic/librewolf/144.0-1/librewolf-144.0-1-windows-x86_64-setup.exe", "/S"
        case "vcredist140":
            return "https://aka.ms/vs/17/release/vc_redist.x64.exe", "/quiet /norestart"
        case _:
            return None



def _install_from_src(pkg_id: str, display_name: str):
	print(f"Installing {display_name} ({pkg_id}) from source.")
	link = get_link_and_flags("googlechrome")
	if link is not None:
		urllib.request.urlretrieve(link, os.path.join(os.environ.get('TEMP', tempfile.gettempdir()), "item-install.exe"))
		subprocess.run([os.path.join(os.environ.get('TEMP', tempfile.gettempdir()), "item-install.exe")), params.split()])




def install_vcredist():
	# Some people may say see this and say "why is a DEBLOATER installing BLOAT!?"
	# This step is necessary to install dependencies that a very, very large amount of
	# modern programs rely on. For example, Waterfox. These dependencies cannot reasonably
	# be considered "bloat" as bloat is unnecessary, while these dependencies, a very large
	# amount of the time, are necessary.

	#_install_choco_package("vcredist140", "Microsoft Visual C++ 2015–2022 Redistributable")
	_install_from_src("vcredist140", "Microsoft Visual C++ 2015-2022 Resistributable")



def install_browser(pkg_id: str):
	_install_from_src(pkg_id, f"browser '{pkg_id}'")



def main():
	try:
		pkg_id = load_choice()
		logger.info(f"Browser selected: {pkg_id}")
	except Exception as e:
		logger.error(f"Error reading browser choice: {e}")
		show_error_popup(f"Internal error reading browser choice:\n{e}", allow_continue=False)
		sys.exit(1)
	#ensure_chocolatey()
	install_vcredist()
	install_browser(pkg_id)



if __name__ == "__main__":
	main()