import sys
import winreg
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from utilities.util_modify_registry import set_value



def main():
    registry_modifications = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
         "TaskbarAl", winreg.REG_DWORD, 0),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
         "AppsUseLightTheme", winreg.REG_DWORD, 0),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
         "SystemUsesLightTheme", winreg.REG_DWORD, 0),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
         "AppCaptureEnabled", winreg.REG_DWORD, 0),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\PolicyManager\default\ApplicationManagement\AllowGameDVR",
         "Value", winreg.REG_DWORD, 0),
        (winreg.HKEY_CURRENT_USER,
         r"Control Panel\Desktop",
         "MenuShowDelay", winreg.REG_SZ, "0"),
        (winreg.HKEY_CURRENT_USER,
         r"Control Panel\Desktop\WindowMetrics",
         "MinAnimate", winreg.REG_DWORD, 0),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
         "ExtendedUIHoverTime", winreg.REG_DWORD, 1),
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
         "HideFileExt", winreg.REG_DWORD, 0),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Policies\Microsoft\Windows\Psched",
         "NonBestEffortLimit", winreg.REG_DWORD, 0),  # Disables reserved bandwith
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
         "NetworkThrottlingIndex", winreg.REG_DWORD, 0xFFFFFFFF),  # Disables network throttling
    ]
    for hive, key_path, name, value_type, value in registry_modifications:
        try:
            logger.info(f"Applying registry tweak: {key_path}\\{name} = {value!r} (type={value_type})")
            set_value(hive, key_path, name, value, value_type)
            logger.info(f"Successfully set {name}")
        except Exception as e:
            logger.error(f"Failed to apply registry tweak {name}: {e}")
            try:
                show_error_popup(
                    f"Failed to apply registry tweak:\n{key_path}\\{name}\n\n{e}",
                    allow_continue=False
                )
            except Exception:
                pass
            sys.exit(1)

    logger.info("All registry tweaks applied successfully.")



if __name__ == "__main__":
    main()
