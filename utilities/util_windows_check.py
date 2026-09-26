import sys
import winreg
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from configuration_components.localization import t



def _read_registry_value(name: str) -> str:
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    access = winreg.KEY_READ
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access |= winreg.KEY_WOW64_64KEY
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, access) as key:
            val, _ = winreg.QueryValueEx(key, name)
        return str(val)
    except Exception as e:
        logger.exception(f"Unable to read registry value {name}: {e}")
        raise


def supports_group_policy(*, strict: bool = True) -> bool:
    if sys.platform != "win32":
        return False
    try:
        edition = _read_registry_value("EditionID").strip().casefold()
    except Exception:
        logger.warning("Unable to determine Group Policy availability", exc_info=True)
        if strict:
            raise
        return False
    supported = edition in {
        "professional", "professionaln", "professionaleducation",
        "professionaleducationn", "professionalworkstation", "professionalworkstationn",
        "enterprise", "enterprisen", "enterprises", "enterprisesn",
        "enterpriseg", "enterprisegn", "education", "educationn",
        "iotenterprise", "iotenterprises",
    }
    if strict and not supported and edition not in {"core", "coren", "coresinglelanguage", "corecountryspecific"}:
        raise ValueError(f"Unrecognized Windows edition: {edition}")
    return supported



def check_windows_11_home_or_pro() -> str:
    if sys.platform != "win32":
        show_error_popup(
            t("errors.unsupported_os"),
            allow_continue=False
        )
    try:
        product_name = _read_registry_value("ProductName")
        build_str    = _read_registry_value("CurrentBuildNumber")
        build_num    = int(build_str)
    except Exception:
        show_error_popup(
            t("errors.windows_version_failed"),
            allow_continue=False
        )
    is_win11 = (
        product_name.startswith("Windows 11")
        or (product_name.startswith("Windows 10") and build_num >= 22000)
    )
    if not is_win11:
        show_error_popup(
            t("errors.incompatible_windows_version", {"product_name": product_name, "build_num": build_num}),
            allow_continue=False
        )
    logger.info(f"Detected OS: {product_name} (build {build_num})")
    return product_name



if __name__ == "__main__":
    ed = check_windows_11_home_or_pro()
    logger.info(f"Windows 11 {ed} detected. Continuing…")
