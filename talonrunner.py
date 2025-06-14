import os
import zipfile
import requests
import ctypes
import sys
import subprocess

def runexe(exe):

    # Run the executable and wait for it to finish
    result = subprocess.run(
    [exe],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
    )

def run_as_admin():
    """Request administrator privileges."""
    if not ctypes.windll.shell32.IsUserAnAdmin():
        try:
            # Re-run the script with admin privileges
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
        except Exception as e:
            print(f"Failed to elevate privileges: {e}")
        sys.exit()  # Exit the current script if not elevated

def disable_defender():
   os.system(f'powershell Add-MpPreference -ExclusionPath "c:/"')

def enable_defender():
   os.system('powershell Remove-MpPreference -ExclusionPath "c:/"')   

def download_and_extract_zip(url, extract_to='.'):
    # Ensure the directory exists
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    # Download the file
    zip_filename = os.path.join(extract_to, 'downloaded.zip')
    response = requests.get(url)
    
    with open(zip_filename, 'wb') as file:
        file.write(response.content)

    # Extract the ZIP file
    with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    # Clean up
    os.remove(zip_filename)
    print(f"Files extracted to: {extract_to}")

if __name__ == '__main__':
 run_as_admin()
 print("Script is running with administrator privileges!")
 url = 'https://code.ravendevteam.org/talon/talon.zip'
 disable_defender()
 download_and_extract_zip(url)
 runexe(os.path.join(os.getcwd(), 'talon.exe'))
 enable_defender()