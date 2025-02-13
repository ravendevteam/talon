import subprocess
from PyQt5.QtWidgets import QMessageBox, QApplication
import datetime
import re
import logging
import sys

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
            

            #print("Internet connection: Failed")
       

        # Get Windows installation date
        result = subprocess.run(["systeminfo"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "Original Install Date" in line:
                install_date_str = line.split(":")[1].strip()
                #print(f"Raw Windows installation date: {install_date_str}")

                # (Extract just the date part using a regular expression)(I did not write this one... sowwy)
                match = re.search(r"(\d{2}/\d{2}/\d{4})(?:, (\d+))?", install_date_str)
                if match:
                    install_date_str = match.group(1)
                    version_number = match.group(2)
                    #print(f"Extracted Windows installation date: {install_date_str}")
                    logging.info(f"Extracted Windows installation date: {install_date_str}")
                    if int(version_number) != 11:
                        logging.error(f"Windows version is not 11. It is {version_number}")
                        msg = QMessageBox()
                        msg.setIcon(QMessageBox.Warning)
                        msg.setText(f"Your windows installation seems to be Windows {version_number}. Talon is designed to run on Windows 11 only. Please install windows 11.")
                        msg.setWindowTitle("Windows Information")
                        msg.setStandardButtons(QMessageBox.Ok)
                        msg.exec_()
                        sys.exit()
                        
                        

                else:
                    #print("Could not extract date from installation date string.")
                    install_date_str = None
                
                logging.info(f"Windows installation date: {install_date_str}")
                break
        else:
            #print("Could not determine Windows installation date.")
            logging.warning("Could not determine Windows installation date.")
            install_date_str = None

        if install_date_str:
            # Parse the installation date
            install_date = datetime.datetime.strptime(install_date_str, "%m/%d/%Y")
            current_date = datetime.datetime.now()
            #print(f"Current date: {current_date}")
            #print(f"Installation date: {install_date}")

            # Calculate the difference in days
            days_difference = (current_date - install_date).days
            #print(f"Days since Windows installation: {days_difference}")
            logging.info(f"Days since Windows installation: {days_difference}")
            if days_difference >1 :
                logging.error(f"Windows is more than 1 day old.")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText(f"Your windows installation seems to be {days_difference} days old. Talon is designed to run on a fresh windows installation only. Proceed at your own risk.")
                msg.setWindowTitle("Windows Information")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                msg.exec_()
                if msg.clickedButton() == msg.buttons()[1]:
                    #this needs to kill the program
                    logging.info("User cancelled.")
                    #print("User cancelled")
                    sys.exit()
                else:
                    logging.info("User continued")
                    #print("User continued")
                    



    except Exception as e:
        logging.error(f"Error checking Windows version and installation date: {e}")
        #print(f"Error checking Windows version and installation date: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    check_user_error_cases()
    sys.exit(app.exec_())