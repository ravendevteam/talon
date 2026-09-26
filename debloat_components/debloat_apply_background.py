import os
import sys
import ctypes
from utilities.util_logger import logger
from utilities.util_error_popup import show_error_popup
from configuration_components.localization import t


def main(applied_background_path=None):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        components_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(components_dir)
    media_dir = os.path.join(base_path, 'media')
    custom_path = str(applied_background_path or "").strip()
    wallpaper_path = os.path.abspath(custom_path) if custom_path else os.path.join(media_dir, 'desktop_background.png')
    logger.info(f"Setting desktop background: {wallpaper_path}")
    if not os.path.exists(wallpaper_path):
        msg = t("errors.wallpaper_not_found", {"path": wallpaper_path})
        logger.error(msg)
        show_error_popup(msg, allow_continue=True)
        return
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE   = 0x01
    SPIF_SENDCHANGE      = 0x02
    try:
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            wallpaper_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        if not result:
            raise ctypes.WinError()
        logger.info("Desktop background set successfully.")
    except Exception as e:
        logger.error(f"Failed to set desktop background: {e}")
        show_error_popup(t("errors.desktop_background_failed", {"error": e}), allow_continue=True)
        return



if __name__ == "__main__":
    main()
