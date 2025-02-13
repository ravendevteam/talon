import sys
import ctypes
import os
import tempfile
import subprocess
import requests
import winreg
import shutil
import time
import logging
import json

LOG_FILE = "talon.txt"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def log(message):
    logging.info(message)
    print(message)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)

def apply_registry_changes():
    log("Applying registry changes...")
    try:
        registry_modifications = [
            # Visual changes
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarAl", winreg.REG_DWORD, 0), # Align taskbar to the left
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", "AppsUseLightTheme", winreg.REG_DWORD, 0), # Set Windows to dark theme
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", "SystemUsesLightTheme", winreg.REG_DWORD, 0), # Set Windows to dark theme
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent", "AccentColorMenu", winreg.REG_DWORD, 1), # Makes accent color the color of the taskbar and start menu (1)  --.
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\Personalize", "ColorPrevalence", winreg.REG_DWORD, 1), # Makes accent color the color of the taskbar and start menu (2)   |-- These are redundant. I know
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\DWM", "AccentColorInStartAndTaskbar", winreg.REG_DWORD, 1), # Makes accent color the color of the taskbar and start menu (3)                   --'
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent", "AccentPalette", winreg.REG_BINARY, b"\x00" * 32), # Makes the taskbar black
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "AppCaptureEnabled", winreg.REG_DWORD, 0), #Fix the  Get an app for 'ms-gamingoverlay' popup
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\PolicyManager\\default\\ApplicationManagement\\AllowGameDVR", "Value", winreg.REG_DWORD, 0), # Disable Game DVR (Reduces FPS Drops)
            (winreg.HKEY_CURRENT_USER, r"Control Panel\\Desktop", "MenuShowDelay", winreg.REG_SZ, "0"),# Reduce menu delay for snappier UI
            (winreg.HKEY_CURRENT_USER, r"Control Panel\\Desktop\\WindowMetrics", "MinAnimate", winreg.REG_DWORD, 0),# Disable minimize/maximize animations
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ExtendedUIHoverTime", winreg.REG_DWORD, 1),# Reduce hover time for tooltips and UI elements
            (winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "HideFileExt", winreg.REG_DWORD, 0),# Show file extensions in Explorer (useful for security and organization)
        ]
        for root_key, key_path, value_name, value_type, value in registry_modifications:
            try:
                with winreg.CreateKeyEx(root_key, key_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, value_name, 0, value_type, value)
                    log(f"Applied {value_name} to {key_path}")
            except Exception as e:
                log(f"Failed to modify {value_name} in {key_path}: {e}")
        log("Registry changes applied successfully.")
        subprocess.run(["taskkill", "/F", "/IM", "explorer.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["start", "explorer.exe"], shell=True)
        log("Explorer restarted to apply registry changes.")
        run_edge_vanisher()
        log("Edge Vanisher started successfully")
        
    except Exception as e:
        log(f"Error applying registry changes: {e}")

def run_edge_vanisher():
    log("Starting Edge Vanisher script execution...")
    try:
        script_url = "https://raw.githubusercontent.com/ravendevteam/talon-blockedge/refs/heads/main/edge_vanisher.ps1"
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, "edge_vanisher.ps1")
        log(f"Attempting to download Edge Vanisher script from: {script_url}")
        log(f"Target script path: {script_path}")
        
        response = requests.get(script_url)
        log(f"Download response status code: {response.status_code}")
        
        with open(script_path, "wb") as file:
            file.write(response.content)
        log("Edge Vanisher script successfully saved to disk")
        
        powershell_command = (
            f"Set-ExecutionPolicy Bypass -Scope Process -Force; "
            f"& '{script_path}'; exit" 
        )
        log(f"Executing PowerShell command: {powershell_command}")
        
        process = subprocess.run(
            ["powershell", "-Command", powershell_command],
            capture_output=True,
            text=True
        )
        
        if process.returncode == 0:
            log("Edge Vanisher execution completed successfully")
            log(f"Process output: {process.stdout}")
            run_oouninstall()
        else:
            log(f"Edge Vanisher execution failed with return code: {process.returncode}")
            log(f"Process error: {process.stderr}")
            run_oouninstall()
            
    except requests.exceptions.RequestException as e:
        log(f"Network error during Edge Vanisher script download: {str(e)}")
        run_oouninstall()
    except IOError as e:
        log(f"File I/O error while saving Edge Vanisher script: {str(e)}")
        run_oouninstall()
    except Exception as e:
        log(f"Unexpected error during Edge Vanisher execution: {str(e)}")
        run_oouninstall()

def run_oouninstall():
    log("Starting Office Online uninstallation process...")
    try:
        script_url = "https://raw.githubusercontent.com/ravendevteam/oouninstaller/refs/heads/main/uninstall_oo.ps1"
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, "uninstall_oo.ps1")
        log(f"Attempting to download OO uninstall script from: {script_url}")
        log(f"Target script path: {script_path}")
        
        response = requests.get(script_url)
        log(f"Download response status code: {response.status_code}")
        
        with open(script_path, "wb") as file:
            file.write(response.content)
        log("OO uninstall script successfully saved to disk")
        
        powershell_command = f"Set-ExecutionPolicy Bypass -Scope Process -Force; & '{script_path}'"
        log(f"Executing PowerShell command: {powershell_command}")
        
        process = subprocess.run(
            ["powershell", "-Command", powershell_command],
            capture_output=True,
            text=True
        )
        
        if process.returncode == 0:
            log("Office Online uninstallation completed successfully")
            log(f"Process stdout: {process.stdout}")
            run_tweaks()
        else:
            log(f"Office Online uninstallation failed with return code: {process.returncode}")
            log(f"Process stderr: {process.stderr}")
            log(f"Process stdout: {process.stdout}")
            run_tweaks()
            
    except Exception as e:
        log(f"Unexpected error during OO uninstallation: {str(e)}")
        run_tweaks()

def run_tweaks():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if not is_admin():
        log("Must be run as an administrator.")
        sys.exit(1)

    try:
        config_url = "https://raw.githubusercontent.com/ravendevteam/talon/refs/heads/main/barebones.json"
        log(f"Downloading config from: {config_url}")
        response = requests.get(config_url)
        config = json.loads(response.content.decode('utf-8-sig'))
        
        temp_dir = tempfile.gettempdir()
        json_path = os.path.join(temp_dir, "custom_config.json")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)

        log_file = os.path.join(temp_dir, "cttwinutil.log")
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$ErrorActionPreference = 'SilentlyContinue'; " +
            f"iex \"& {{ $(irm christitus.com/win) }} -Config '{json_path}' -Run\" *>&1 | " +
            "Tee-Object -FilePath '" + log_file + "'"
        ]
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        while True:
            output = process.stdout.readline()
            if output:
                output = output.strip()
                log(f"CTT Output: {output}")
                if "Tweaks are Finished" in output:
                    log("Detected completion message. Terminating...")

                    subprocess.run(
                        ["powershell", "-Command", "Stop-Process -Name powershell -Force"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )

                    run_applybackground()
                    os._exit(0)
            
            if process.poll() is not None:
                run_applybackground()
                os._exit(1)

        return False

    except Exception as e:
        log(f"Error: {str(e)}")
        run_applybackground()
        os._exit(1)

def run_applybackground():
    log("Starting ApplyBackground tweaks...")
    try:
        temp_dir = tempfile.gettempdir()
        exe_name = "applybackground.exe"
        exe_path = os.path.join(temp_dir, exe_name)
        url = "https://github.com/ravendevteam/talon-applybackground/releases/download/v1.0.0/applybackground.exe"
        download_success = False
        for attempt in range(3):
            try:
                log(f"Downloading {exe_name} (Attempt {attempt + 1}/3)...")
                response = requests.get(url, stream=True, timeout=10)
                if response.status_code == 200:
                    with open(exe_path, "wb") as file:
                        for chunk in response.iter_content(chunk_size=8192):
                            file.write(chunk)
                    log(f"Download complete: {exe_path}")
                    download_success = True
                    break
                else:
                    log(f"Download failed with status code: {response.status_code}")
            except Exception as e:
                log(f"Download attempt {attempt + 1} failed: {e}")
                time.sleep(3)

        if not download_success:
            log("Failed to download ApplyBackground")
            run_winconfig()
            return

        if not os.path.exists(exe_path):
            log(f"ApplyBackground not found at: {exe_path}")
            run_winconfig()
            return

        log(f"Running ApplyBackground from: {exe_path}")
        process = subprocess.run(
            [exe_path],
            capture_output=True,
            text=True
        )

        if process.returncode == 0:
            log("ApplyBackground applied successfully")
        else:
            log(f"Error applying ApplyBackground: {process.stderr}")

        log("ApplyBackground complete")
        run_winconfig()

    except Exception as e:
        log(f"Error in ApplyBackground: {str(e)}")
        run_winconfig()

def run_winconfig():
    log("Starting Windows configuration process...")
    try:
        script_url = "https://win11debloat.raphi.re/"
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, "Win11Debloat.ps1")
        log(f"Attempting to download Windows configuration script from: {script_url}")
        log(f"Target script path: {script_path}")
        
        response = requests.get(script_url)
        log(f"Download response status code: {response.status_code}")
        
        with open(script_path, "wb") as file:
            file.write(response.content)
        log("Windows configuration script successfully saved to disk")
        
        powershell_command = (
            f"Set-ExecutionPolicy Bypass -Scope Process -Force; "
            f"& '{script_path}' -Silent -RemoveApps -RemoveGamingApps -DisableTelemetry "
            f"-DisableBing -DisableSuggestions -DisableLockscreenTips -RevertContextMenu "
            f"-TaskbarAlignLeft -HideSearchTb -DisableWidgets -DisableCopilot -ExplorerToThisPC"
        )
        log(f"Executing PowerShell command with parameters:")
        log(f"Command: {powershell_command}")
        
        process = subprocess.run(
            ["powershell", "-Command", powershell_command],
            capture_output=True,
            text=True
        )
        
        if process.returncode == 0:
            log("Windows configuration completed successfully")
            log(f"Process stdout: {process.stdout}")
            log("Preparing to transition to UpdatePolicyChanger...")
            try:
                log("Initiating UpdatePolicyChanger process...")
                run_updatepolicychanger()
            except Exception as e:
                log(f"Failed to start UpdatePolicyChanger: {e}")
                log("Attempting to continue with installation despite UpdatePolicyChanger failure")
                run_updatepolicychanger()
        else:
            log(f"Windows configuration failed with return code: {process.returncode}")
            log(f"Process stderr: {process.stderr}")
            log(f"Process stdout: {process.stdout}")
            log("Attempting to continue with UpdatePolicyChanger despite WinConfig failure")
            try:
                log("Initiating UpdatePolicyChanger after WinConfig failure...")
                run_updatepolicychanger()
            except Exception as e:
                log(f"Failed to start UpdatePolicyChanger after WinConfig failure: {e}")
                log("Proceeding to finalize installation...")
                run_updatepolicychanger()
            
    except requests.exceptions.RequestException as e:
        log(f"Network error during Windows configuration script download: {str(e)}")
        log("Attempting to continue with UpdatePolicyChanger despite network error")
        try:
            run_updatepolicychanger()
        except Exception as inner_e:
            log(f"Failed to start UpdatePolicyChanger after network error: {inner_e}")
            run_updatepolicychanger()
    except IOError as e:
        log(f"File I/O error while saving Windows configuration script: {str(e)}")
        log("Attempting to continue with UpdatePolicyChanger despite I/O error")
        try:
            run_updatepolicychanger()
        except Exception as inner_e:
            log(f"Failed to start UpdatePolicyChanger after I/O error: {inner_e}")
            run_updatepolicychanger()
    except Exception as e:
        log(f"Unexpected error during Windows configuration: {str(e)}")
        log("Attempting to continue with UpdatePolicyChanger despite unexpected error")
        try:
            run_updatepolicychanger()
        except Exception as inner_e:
            log(f"Failed to start UpdatePolicyChanger after unexpected error: {inner_e}")
            run_updatepolicychanger()

def run_updatepolicychanger():
    log("Starting UpdatePolicyChanger script execution...")
    log("Checking system state before UpdatePolicyChanger execution...")
    try:
        script_url = "https://raw.githubusercontent.com/ravendevteam/talon-updatepolicy/refs/heads/main/UpdatePolicyChanger.ps1"
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, "UpdatePolicyChanger.ps1")
        log(f"Attempting to download UpdatePolicyChanger script from: {script_url}")
        log(f"Target script path: {script_path}")
        
        try:
            response = requests.get(script_url)
            log(f"Download response status code: {response.status_code}")
            log(f"Response headers: {response.headers}")
            
            if response.status_code != 200:
                log(f"Unexpected status code: {response.status_code}")
                raise requests.exceptions.RequestException(f"Failed to download: Status code {response.status_code}")
                
            content_length = len(response.content)
            log(f"Downloaded content length: {content_length} bytes")
            
            with open(script_path, "wb") as file:
                file.write(response.content)
            log("UpdatePolicyChanger script successfully saved to disk")
            log(f"Verifying file exists at {script_path}")
            
            if not os.path.exists(script_path):
                raise IOError("Script file not found after saving")
            
            file_size = os.path.getsize(script_path)
            log(f"Saved file size: {file_size} bytes")
            
        except requests.exceptions.RequestException as e:
            log(f"Network error during script download: {e}")
            raise
        
        log("Preparing PowerShell command execution...")
        powershell_command = (
            f"Set-ExecutionPolicy Bypass -Scope Process -Force; "
            f"& '{script_path}'; exit" 
        )
        log(f"PowerShell command prepared: {powershell_command}")
        
        try:
            log("Executing PowerShell command...")
            process = subprocess.run(
                ["powershell", "-Command", powershell_command],
                capture_output=True,
                text=True,
            )
            
            log(f"PowerShell process completed with return code: {process.returncode}")
            log(f"Process stdout length: {len(process.stdout)}")
            log(f"Process stderr length: {len(process.stderr)}")
            
            if process.stdout:
                log(f"Process output: {process.stdout}")
            if process.stderr:
                log(f"Process errors: {process.stderr}")
            
            if process.returncode == 0:
                log("UpdatePolicyChanger execution completed successfully")
                log("Preparing to finalize installation...")
                finalize_installation()
            else:
                log(f"UpdatePolicyChanger execution failed with return code: {process.returncode}")
                log("Proceeding with finalization despite failure...")
                finalize_installation()
                
        except subprocess.TimeoutExpired:
            log("PowerShell command execution timed out after 5 minutes")
            finalize_installation()
        except subprocess.SubprocessError as e:
            log(f"Error executing PowerShell command: {e}")
            finalize_installation()
            
    except Exception as e:
        log(f"Critical error in UpdatePolicyChanger: {e}")
        log("Proceeding to finalization due to critical error...")
        finalize_installation()


def finalize_installation():
    log("Installation complete. Restarting system...")
    try:
        subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
    except subprocess.CalledProcessError as e:
        log(f"Error during restart: {e}")
        try:
            os.system("shutdown /r /t 0")
        except Exception as e:
            log(f"Failed to restart system: {e}")

if __name__ == "__main__":
    apply_registry_changes()
