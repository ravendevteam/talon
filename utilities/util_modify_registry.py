import winreg
from typing import Any, Union, Optional
from utilities.util_logger import logger



VIEW_FLAG = winreg.KEY_WOW64_64KEY if hasattr(winreg, 'KEY_WOW64_64KEY') else 0
_HIVE_MAPPING = {
    'HKLM': winreg.HKEY_LOCAL_MACHINE,
    'HKEY_LOCAL_MACHINE': winreg.HKEY_LOCAL_MACHINE,
    'HKCU': winreg.HKEY_CURRENT_USER,
    'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER,
    'HKCR': winreg.HKEY_CLASSES_ROOT,
    'HKEY_CLASSES_ROOT': winreg.HKEY_CLASSES_ROOT,
    'HKU': winreg.HKEY_USERS,
    'HKEY_USERS': winreg.HKEY_USERS,
    'HKCC': winreg.HKEY_CURRENT_CONFIG,
    'HKEY_CURRENT_CONFIG': winreg.HKEY_CURRENT_CONFIG,
}



def _resolve_hive(hive: Union[str, int]) -> int:
    if isinstance(hive, int):
        return hive
    key = hive.upper()
    if key in _HIVE_MAPPING:
        return _HIVE_MAPPING[key]
    raise ValueError(f"Unknown registry hive: {hive!r}")



def set_value(
    hive: Union[str, int],
    key_path: str,
    name: str,
    value: Any,
    value_type: Optional[int] = None
) -> None:
    try:
        hive_const = _resolve_hive(hive)
        if value_type is None:
            if isinstance(value, int):
                value_type = winreg.REG_DWORD
            elif isinstance(value, str):
                value_type = winreg.REG_SZ
            elif isinstance(value, bytes):
                value_type = winreg.REG_BINARY
            else:
                raise ValueError(f"Unsupported registry value type: {type(value)}")
        access = winreg.KEY_WRITE | VIEW_FLAG
        with winreg.CreateKeyEx(hive_const, key_path, 0, access) as key:
            winreg.SetValueEx(key, name, 0, value_type, value)
        logger.info(f"Set registry value: {hive}\\{key_path}\\{name} = {value!r} (type={value_type})")
    except Exception as e:
        logger.exception(f"Error setting registry value {hive}\\{key_path}\\{name}: {e}")
        raise
