import os
import re
import subprocess
import sys

from configuration_components.localization import t
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger
from utilities.util_powershell_handler import run_powershell_command
from utilities.util_process import run_logged_process


_PACKAGE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}", re.ASCII)


def normalize_chocolatey_packages(value) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(t("errors.chocolatey_packages_type"))
    packages = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(t("errors.chocolatey_packages_type"))
        package = item.strip().lower()
        if (
            not _PACKAGE_ID.fullmatch(package)
            or package == "all"
            or package.endswith((".config", ".nupkg", ".nuspec"))
        ):
            raise ValueError(t("errors.chocolatey_package_invalid", {"package": item}))
        if package not in seen:
            packages.append(package)
            seen.add(package)
    return packages


def get_choco_exe() -> str:
    env_path = os.environ.get("ChocolateyInstall")
    if env_path:
        choco = os.path.join(env_path, "bin", "choco.exe")
        if os.path.isfile(choco):
            return choco
    default_path = os.path.join(
        os.environ.get("ProgramData", r"C:\ProgramData"),
        "chocolatey", "bin", "choco.exe",
    )
    return default_path if os.path.isfile(default_path) else "choco"


def ensure_chocolatey():
    try:
        try:
            run_logged_process(
                [get_choco_exe(), "-v"],
                check=True,
                label="Chocolatey version check",
            )
            logger.info("Chocolatey already installed.")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.info("Chocolatey not found. Installing now...")

        install_cmd = (
            "Set-ExecutionPolicy Bypass -Scope Process -Force; "
            "[System.Net.ServicePointManager]::SecurityProtocol = "
            "[System.Net.ServicePointManager]::SecurityProtocol -bor 3072; "
            "iex ((New-Object System.Net.WebClient).DownloadString("
            "'https://community.chocolatey.org/install.ps1'))"
        )
        run_powershell_command(install_cmd)
        run_logged_process(
            [get_choco_exe(), "-v"],
            check=True,
            label="Chocolatey installation verification",
        )
        logger.info("Chocolatey installed and verified.")
    except Exception as error:
        logger.exception(f"Failed to install or verify Chocolatey: {error}")
        show_error_popup(
            t("errors.chocolatey_install_failed", {"error": error}),
            allow_continue=False,
        )
        sys.exit(1)


def install_choco_package(pkg_id: str, display_name: str = None) -> bool:
    pkg_id = normalize_chocolatey_packages([pkg_id])[0]
    display_name = display_name or pkg_id
    logger.info(f"Installing via Chocolatey: {display_name} ({pkg_id})")
    try:
        result = run_logged_process(
            [get_choco_exe(), "install", pkg_id, "-y", "--use-package-exit-codes"],
            check=False,
            label=f"Chocolatey install {pkg_id}",
        )
    except Exception as error:
        logger.exception(f"Unexpected error installing {pkg_id}: {error}")
        show_error_popup(
            t("errors.chocolatey_package_error", {"display_name": display_name, "error": error}),
            allow_continue=True,
        )
        return False

    if result.returncode == 3010:
        logger.info(f"Successfully installed {display_name}, reboot required.")
        return True
    if result.returncode == 1641:
        logger.warning(f"Successfully installed {display_name}; the installer initiated a reboot.")
        return True
    if result.returncode == 0:
        logger.info(f"Successfully installed {display_name}.")
        return True
    logger.error(f"Chocolatey exited with code {result.returncode} for {pkg_id}")
    show_error_popup(
        t("errors.chocolatey_package_failed", {"display_name": display_name, "exit_code": result.returncode}),
        allow_continue=True,
    )
    return False
