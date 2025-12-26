import sys, os
from utilities.util_logger import logger
from utilities.util_powershell_handler import run_powershell_script
from utilities.util_error_popup import show_error_popup



def main():
    scripts = [
        "edge_vanisher.ps1",
        "uninstall_oo.ps1",
    ]
    for script in scripts:
        logger.info(f"Executing PowerShell script: {script}")
        try:
            run_powershell_script(script)
            logger.info(f"Successfully executed {script}")
        except Exception as e:
            logger.error(f"Failed to execute {script}: {e}")
            try:
                show_error_popup(
                    f"Failed to execute PowerShell script:\n{script}\n\n{e}",
                    allow_continue=False
                )
            except Exception:
                pass
            sys.exit(1)

    logger.info("All debloat scripts executed successfully.")



if __name__ == "__main__":
    main()
