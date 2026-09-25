"""i18n — перевод текстов интерфейса victus-suite.

Источники языка (по приоритету):
  1. переменная окружения VICTUS_LANG   (ru / en / ...)
  2. файл config/locale                 (обычно содержит "ru")
  3. по умолчанию                      "ru"

Словари лежат в locales/<код>.json (вложенность: "раздел.ключ": "текст").
Отсутствующий ключ/язык берётся из en.json, затем возвращается сам ключ.

Добавление нового языка:
  1) скопируй locales/ru.json → locales/<код>.json
  2) переведи значения (ключи не трогай)
  3) укажи язык: echo "<код>" > config/locale   или   VICTUS_LANG=<код> команда
"""

import json
import os

_HERE = os.path.dirname(os.path.realpath(__file__))
_PROJECT = os.path.dirname(_HERE) if os.path.basename(_HERE) == "bin" else _HERE
LOCALES_DIR = os.path.join(_PROJECT, "locales")
CONFIG_LOCALE = os.path.join(_PROJECT, "config", "locale")
DEFAULT_LANG = "ru"
FALLBACK_LANG = "en"

_cache = {}


def available():
    """Список установленных языков (коды из имени *.json)."""
    try:
        return sorted(
            f[:-5]
            for f in os.listdir(LOCALES_DIR)
            if f.endswith(".json") and os.path.isfile(os.path.join(LOCALES_DIR, f))
        )
    except OSError:
        return [DEFAULT_LANG]


def _config_lang():
    try:
        with open(CONFIG_LOCALE, encoding="utf-8") as f:
            code = f.read().strip().split()[0].lower()
            if code:
                return code
    except (OSError, IndexError):
        pass
    return None


def lang():
    code = (os.environ.get("VICTUS_LANG") or _config_lang() or DEFAULT_LANG).lower()
    return code if code in available() else DEFAULT_LANG


def _load(code):
    if code in _cache:
        return _cache[code]
    path = os.path.join(LOCALES_DIR, f"{code}.json")
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    _cache[code] = data
    return data


def t(key, **kwargs):
    """Перевод по ключу ("раздел.ключ") + подстановка {параметров}."""
    code = lang()
    text = _load(code).get(key)
    if text is None and code != FALLBACK_LANG:
        text = _load(FALLBACK_LANG).get(key)
    if text is None:
        text = key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
