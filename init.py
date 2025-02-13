import sys
import os
import ctypes
import subprocess
import threading
import logging
from PyQt5.QtWidgets import QApplication
from browser_select_screen import BrowserSelectScreen
from defender_check import DefenderCheck
from raven_app_screen import RavenAppScreen
from install_screen import InstallScreen
import debloat_windows
import raven_software_install
import browser_install
import time
from PyQt5.QtCore import QTimer
import platform
import winreg
import error_checks

TALON_VERSION = "1.1.0"

LOG_FILE = "talon.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_windows_info():
    try:
        windows_version = platform.win32_ver()
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        key = winreg.OpenKey(reg, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        
        build_number = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
        product_name = winreg.QueryValueEx(key, "ProductName")[0]
        display_version = winreg.QueryValueEx(key, "DisplayVersion")[0]
        
        return {
            'version': windows_version[0],
            'build': build_number,
            'product_name': product_name,
            'display_version': display_version
        }
    except Exception as e:
        logging.error(f"Error getting Windows information: {e}")
        return None

def is_running_as_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception as e:
        logging.error(f"Error checking admin privileges: {e}")
        return False

def restart_as_admin():
    try:
        script = sys.argv[0]
        params = ' '.join(sys.argv[1:])
        logging.info("Restarting with admin privileges...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit()
    except Exception as e:
        logging.error(f"Error restarting as admin: {e}")

def main():
    logging.info("Starting Talon Installer")
    logging.info(f"Talon Version: {TALON_VERSION}")
    
    windows_info = get_windows_info()
    if windows_info:
        logging.info(f"Windows Version: {windows_info['product_name']}")
        logging.info(f"Build Number: {windows_info['build']}")
        logging.info(f"Display Version: {windows_info['display_version']}")
    
    app = QApplication(sys.argv)

    if not is_running_as_admin():
        logging.warning("Program is not running as admin. Restarting with admin rights...")
        restart_as_admin()

    try:
        logging.info("Starting Defender check...")
        defender_check_window = DefenderCheck()
        defender_check_window.defender_disabled_signal.connect(defender_check_window.close)
        defender_check_window.show()
        while defender_check_window.isVisible():
            app.processEvents()
        logging.info("Defender is disabled, proceeding with the rest of the program.")
    except Exception as e:
        logging.error(f"Error during Defender check: {e}")

        try:
            logging.info("Checking common errors...")
            error_checks.check_user_error_cases()
            logging.info("User error checks passed, proceeding with the rest of the program.")
        except Exception as e:
            logging.error(f"Error during user error checks: {e}")

    selected_browser = None
    try:
        logging.info("Displaying browser selection screen...")
        browser_select_screen = BrowserSelectScreen()
        browser_select_screen.show()
        while selected_browser is None:
            app.processEvents()
            if browser_select_screen.selected_browser is not None:
                selected_browser = browser_select_screen.selected_browser
        logging.info(f"Browser Selected: {selected_browser}")
        browser_select_screen.close()
    except Exception as e:
        logging.error(f"Error during browser selection: {e}")

    install_raven = None
    try:
        logging.info("Displaying Raven app installation screen...")
        raven_app_screen = RavenAppScreen()
        raven_app_screen.show()
        while install_raven is None:
            app.processEvents()
            if raven_app_screen.selected_option is not None:
                install_raven = raven_app_screen.selected_option
        logging.info(f"Raven App Installation Decision: {'Yes' if install_raven else 'No'}")
        raven_app_screen.close()
    except Exception as e:
        logging.error(f"Error during Raven app installation decision: {e}")

    try:
        logging.info("Displaying installation screen...")
        install_screen = InstallScreen()
        install_screen.show()
    except Exception as e:
        logging.error(f"Error during installation screen setup: {e}")

    def perform_installation():
        try:
            if install_raven:
                logging.info("Installing Raven software...")
                raven_software_install.main()
                logging.info("Raven software installed.")
        except Exception as e:
            logging.error(f"Error during Raven software installation: {e}")

        try:
            logging.info(f"Installing {selected_browser} browser...")
            browser_install.install_browser(selected_browser)
            logging.info(f"{selected_browser} browser installation complete.")
        except Exception as e:
            logging.error(f"Error during browser installation: {e}")

        try:
            logging.info("Applying Windows registry modifications and customizations...")
            debloat_windows.apply_registry_changes()
            logging.info("Debloat and customization complete.")
        except Exception as e:
            logging.error(f"Error applying registry changes: {e}")

        logging.info("All installations and configurations completed.")
        
        install_screen.close()
        logging.info("Installation complete. Restarting system...")
        debloat_windows.finalize_installation()

    try:
        logging.info("Starting installation process in a separate thread...")
        install_thread = threading.Thread(target=perform_installation)
        install_thread.start()
        
        while install_thread.is_alive():
            app.processEvents()
            time.sleep(0.05)
            
    except Exception as e:
        logging.error(f"Error starting installation thread: {e}")

    app.exec_()

if __name__ == "__main__":
    main()
