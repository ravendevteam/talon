import sys

from configuration_components.localization import t
from utilities.util_chocolatey import (
    ensure_chocolatey,
    install_choco_package,
    normalize_chocolatey_packages,
)
from utilities.util_error_popup import show_error_popup
from utilities.util_logger import logger


def main(chocolatey_packages=None):
    try:
        packages = normalize_chocolatey_packages(chocolatey_packages)
        if not packages:
            raise ValueError(t("errors.chocolatey_packages_missing"))
    except ValueError as error:
        logger.error(f"Error reading Chocolatey package metadata: {error}")
        show_error_popup(
            t("errors.chocolatey_packages_error", {"error": error}),
            allow_continue=False,
        )
        sys.exit(1)

    ensure_chocolatey()
    for package in packages:
        install_choco_package(package)


if __name__ == "__main__":
    main()
