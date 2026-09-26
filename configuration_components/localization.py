import json
import os
import sys
from copy import deepcopy

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from utilities.util_logger import logger


DEFAULT_LANGUAGE = "en"

_current_language = DEFAULT_LANGUAGE
_catalog_cache = {}


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidate_locale_dirs():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "locales"))
    candidates.append(os.path.join(_repo_root(), "locales"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "locales"))
    return [os.path.abspath(path) for path in candidates]


def locales_dir() -> str:
    for path in _candidate_locale_dirs():
        if os.path.isdir(path):
            return path
    return _candidate_locale_dirs()[0]


def _deep_get(data: dict, dotted_key: str):
    value = data
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _load_catalog(language: str) -> dict:
    language = str(language or DEFAULT_LANGUAGE)
    if language in _catalog_cache:
        return _catalog_cache[language]
    path = os.path.join(locales_dir(), f"{language}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        if not isinstance(catalog, dict):
            logger.warning("Locale catalog must contain a JSON object: %s", path)
            catalog = {}
    except Exception:
        logger.warning("Unable to load locale catalog: %s", path, exc_info=True)
        catalog = {}
    _catalog_cache[language] = catalog
    return catalog


def available_languages() -> list:
    out = []
    root = locales_dir()
    if not os.path.isdir(root):
        logger.warning("Locale directory is unavailable: %s", root)
        return out
    names = sorted(os.listdir(root), key=lambda name: (name != f"{DEFAULT_LANGUAGE}.json", name.lower()))
    for name in names:
        if not name.endswith(".json"):
            continue
        code = name[:-5]
        catalog = _load_catalog(code)
        meta = catalog.get("meta", {}) if isinstance(catalog.get("meta"), dict) else {}
        out.append(
            {
                "code": code,
                "native_name": str(meta.get("native_name", code)),
                "english_name": str(meta.get("english_name", code)),
                "direction": str(meta.get("direction", "ltr")),
            }
        )
    return out


def set_language(language: str) -> bool:
    global _current_language
    language = str(language or DEFAULT_LANGUAGE)
    path = os.path.join(locales_dir(), f"{language}.json")
    if not os.path.isfile(path):
        logger.warning("Cannot select language %r; locale catalog is unavailable: %s", language, path)
        return False
    _current_language = language
    _load_catalog(language)
    return True


def current_language() -> str:
    return _current_language


def t(key: str, params=None) -> str:
    key = str(key)
    params = dict(params or {})
    value = _deep_get(_load_catalog(_current_language), key)
    if value is None and _current_language != DEFAULT_LANGUAGE:
        value = _deep_get(_load_catalog(DEFAULT_LANGUAGE), key)
    if value is None:
        return key
    if not isinstance(value, str):
        return str(value)
    try:
        return value.format(**params)
    except Exception:
        logger.warning("Unable to format translation %r for language %r", key, _current_language, exc_info=True)
        return value


class LocalizationBridge(QObject):
    languageChanged = pyqtSignal()

    @pyqtProperty(str, notify=languageChanged)
    def currentLanguage(self):
        return current_language()

    @pyqtSlot(result="QVariantList")
    def availableLanguages(self):
        return deepcopy(available_languages())

    @pyqtSlot(str, result=bool)
    def setLanguage(self, language):
        before = current_language()
        ok = set_language(language)
        if ok and current_language() != before:
            self.languageChanged.emit()
        return ok

    @pyqtSlot(str, result=str)
    def t(self, key):
        return t(key)

    @pyqtSlot(str, "QVariantMap", result=str)
    def tf(self, key, params):
        return t(key, params)
