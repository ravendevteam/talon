import platform
import subprocess
from PyQt5.QtWidgets import QMessageBox, QApplication
import datetime
import re
import logging
import sys
import winreg
import wmi
'''
def get_windows_install_date():
    try:
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        print("Registry connected")
        key = winreg.OpenKey(reg, r"SYSTEM\Setup")
        print("Key opened")
        install_date, _ = winreg.QueryValueEx(key, "InstallDate")
        print(f"Install date: {install_date}")
        install_date = datetime.datetime.fromtimestamp(install_date)
        print(f"Install date: {install_date}")
        return install_date
    except FileNotFoundError:
        logging.error("Registry key or value not found.")
        return None
    except Exception as e:
        logging.error(f"Error retrieving Windows install date from registry: {e}")
        return None

def get_windows_install_date():
    try:
        result = subprocess.run(["wmic", "os", "get", "installdate"], capture_output=True, text=True, check=True)
        print(result.stdout)
        install_date_str = ((result.stdout.split('\n')[2]).split('.')[0]).strip()[:8]
        print("#",install_date_str)
        install_date = datetime.datetime.strptime(install_date_str, "%Y%m%d")
        print(install_date)
        logging.info(f"Install date retrieved using wmic: {install_date}")
        return install_date
    except Exception as e:
        logging.error(f"Error retrieving Windows install date using wmic: {e}")
        return None
'''

#K well that was a passion project. Going to bed now. That's what I get for trying to pretend to be a python deveoper
def get_windows_install_date():
    try:
        c = wmi.WMI()
        for os in c.Win32_OperatingSystem():
            install_date_str = os.InstallDate.split('.')[0]
            install_date = datetime.datetime.strptime(install_date_str, "%Y%m%d%H%M%S")
            logging.info(f"Install date retrieved using WMI: {install_date}")
            return install_date
    except Exception as e:
        logging.error(f"Error retrieving Windows install date using WMI: {e}")
        return None
    

def check_user_error_cases():
    try:
        #Pings Github (they need internet)
        try:
            subprocess.check_call(["ping", "-n", "1", "github.com"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info("Internet connection: OK")
            #print("Internet connection: OK")
        except subprocess.CalledProcessError:
            logging.error("Internet connection: Failed")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"Please connnect to the internet before running this program.")
            msg.setWindowTitle("No internet")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            sys.exit()
            
        '''
        # Get Windows installation date from registry
        install_date = get_windows_install_date()
        if install_date is None:
            logging.warning("Could not determine Windows installation date.")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Could not determine Windows installation date.")
            msg.setWindowTitle("Error")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            sys.exit()
        '''
        install_date = get_windows_install_date()
        if install_date is None:
            logging.warning("Could not determine Windows installation date.")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Could not determine Windows installation date.")
            msg.setWindowTitle("Error")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            sys.exit()

        current_date = datetime.datetime.now()
        print(f"Current date: {current_date}")
        print(f"Installation date: {install_date}")

        # Calculate the difference in days
        days_difference = (current_date - install_date).days
        print(f"Days since Windows installation: {days_difference}")
        logging.info(f"Days since Windows installation: {days_difference}")
        if days_difference > 1:
            logging.error("Windows is more than 1 day old.")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"Your Windows installation seems to be {days_difference} days old. Talon is designed to run on a fresh Windows installation only. Proceed at your own risk.")
            msg.setWindowTitle("Windows Information")
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            result = msg.exec_()
            if result == QMessageBox.Cancel:
                logging.info("User cancelled.")
                sys.exit()
            else:
                logging.info("User continued")
                    



    except Exception as e:
        logging.error(f"Error checking Windows version and installation date: {e}")
        #print(f"Error checking Windows version and installation date: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    check_user_error_cases()
    app.quit()
    sys.exit()