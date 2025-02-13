import platform
import subprocess
#from PyQt5.QtWidgets import QMessageBox, QApplication
import datetime
import os
import sys
import re

def check_windows_version_and_install_date():
    try:
        # Get Windows version
        windows_version = platform.version()
        print(f"Windows version: {windows_version}")
        #logging.info(f"Windows version: {windows_version}")

        # Get Windows installation date
        result = subprocess.run(["systeminfo"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "Original Install Date" in line:
                install_date_str = line.split(":")[1].strip()
                print(f"Raw Windows installation date: {install_date_str}")

                # Extract just the date part using a regular expression
                match = re.search(r"\d{2}/\d{2}/\d{4}", install_date_str)
                if match:
                    install_date_str = match.group(0)
                    print(f"Extracted Windows installation date: {install_date_str}")
                else:
                    print("Could not extract date from installation date string.")
                    install_date_str = None
                
                #logging.info(f"Windows installation date: {install_date_str}")
                break
        else:
            print("Could not determine Windows installation date.")
            #logging.warning("Could not determine Windows installation date.")
            install_date_str = None

        if install_date_str:
            # Parse the installation date
            install_date = datetime.datetime.strptime(install_date_str, "%m/%d/%Y")
            current_date = datetime.datetime.now()
            print(f"Current date: {current_date}")
            print(f"Installation date: {install_date}")

            # Calculate the difference in days
            days_difference = (current_date - install_date).days
            print(f"Days since Windows installation: {days_difference}")
            #logging.info(f"Days since Windows installation: {days_difference}")

            # Show warning popup if necessary
            #msg = QMessageBox()
            #msg.setIcon(QMessageBox.Warning)
            #msg.setText(f"Windows version: {windows_version}\nInstallation date: {install_date_str}\nDays since installation: {days_difference}")
            #msg.setWindowTitle("Windows Information")
            #msg.setStandardButtons(QMessageBox.Ok)
            #msg.exec_()

    except Exception as e:
        #logging.error(f"Error checking Windows version and installation date: {e}")
        print(f"Error checking Windows version and installation date: {e}")

if __name__ == "__main__":
    # Change the working directory to the script's directory
    #os.chdir(os.path.dirname(os.path.abspath(__file__)))

    #app = QApplication([])
    check_windows_version_and_install_date()
    #app.exec_()