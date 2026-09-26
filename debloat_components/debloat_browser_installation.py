import sys

from configuration_components.localization import t
from utilities.util_chocolatey import (
    ensure_chocolatey,
    install_choco_package,
    normalize_chocolatey_packages,
)
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger


def install_vcredist():
    install_choco_package("vcredist140", "Microsoft Visual C++ 2015\u20132022 Redistributable")


def install_browser(pkg_id: str):
    install_choco_package(pkg_id, f"browser '{pkg_id}'")


def main(selected_browser_package=None):
    try:
        if not selected_browser_package:
            raise ValueError(t("errors.browser_metadata_missing"))
        pkg_id = normalize_chocolatey_packages([selected_browser_package])[0]
        logger.info(f"Browser selected: {pkg_id}")
    except Exception as error:
        logger.error(f"Error reading browser choice metadata: {error}")
        show_error_popup(t("errors.browser_metadata_error", {"error": error}), allow_continue=False)
        sys.exit(1)
    ensure_chocolatey()
    install_vcredist()
    install_browser(pkg_id)


if __name__ == "__main__":
    main()
