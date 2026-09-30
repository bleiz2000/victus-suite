"""Мост TUI ↔ vertil: телеметрия и запись вентиляторов.

Чтение — fanlib.Sensors (userspace, без root, вызывается в потоке: nvidia-smi
дергает до ~3 с). Запись — vertil/tools/fanctl.py; без root идут через
`sudo -n bin/victus-kbd fans …`, то есть через уже выданное NOPASSWD-правилом
право на victus-kbd (README) — пароль не спрашивается. Если правила нет,
`sudo -n` сразу падает и TUI честно говорит «нужен sudo -v».

session — флаги, которые переживают пересборку вкладки (смена языка):
  controlled — мы уже меняли железо в этой сессии (тогда на выходе держим
               безопасный PWM, см. presets.safety.hold_pwm_on_controller_loss);
  autopilot  — включён SMART-цикл.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import victus_log as vlog

TOOL = "vertil"

_HERE = os.path.dirname(os.path.realpath(__file__))
_BIN = os.path.dirname(_HERE)
_PROJECT = os.path.dirname(_BIN)
TOOLS = os.path.join(_PROJECT, "vertil", "tools")
FANCTL = os.path.join(TOOLS, "fanctl.py")
KBD = os.path.join(_BIN, "victus-kbd")

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

try:
    import fanlib
except Exception:  # noqa: BLE001 — каталог vertil/ может отсутствовать
    fanlib = None

session = {"controlled": False, "autopilot": False}

_access = None
_fans = None
_sensors = None
_busy_prev = None


def available() -> bool:
    """Есть ли backend (fanlib + fanctl.py) и найден ли hp-hwmon."""
    return bool(fanlib is not None and os.path.exists(FANCTL))


def preset() -> dict:
    if fanlib is None:
        return {}
    try:
        return fanlib.load_preset()
    except (OSError, ValueError) as e:
        vlog.log("warn", TOOL, f"preset load failed: {e}")
        return {}


def hold_pwm() -> int:
    """Уровень «контроллер умер» — presets.safety.hold_pwm_on_controller_loss."""
    try:
        return int(preset()["safety"]["hold_pwm_on_controller_loss"])
    except (KeyError, TypeError, ValueError):
        return 180


def max_rpm() -> int:
    try:
        return int(preset()["device"]["max_cpu_rpm"])
    except (KeyError, TypeError, ValueError):
        return 5800


def _fans_obj():
    global _fans
    if fanlib is None:
        return None
    if _fans is None or not getattr(_fans, "hp", None):
        try:
            _fans = fanlib.Fans(preset() or None)
        except Exception as e:  # noqa: BLE001
            vlog.log("warn", TOOL, f"fans init failed: {e}")
            return None
    return _fans


def _sensors_obj():
    global _sensors
    if fanlib is None:
        return None
    if _sensors is None or not getattr(_sensors.fans, "hp", None):
        try:
            _sensors = fanlib.Sensors(preset() or None)
        except Exception as e:  # noqa: BLE001
            vlog.log("warn", TOOL, f"sensors init failed: {e}")
            return None
    return _sensors


def snapshot() -> dict | None:
    """Один снимок телеметрии. Блокирующее (nvidia-smi) — звать в потоке."""
    global _busy_prev
    if not available():
        return None
    sensors = _sensors_obj()
    if sensors is None:
        return None
    try:
        data = sensors.read(_busy_prev)
    except Exception as e:  # noqa: BLE001
        vlog.log("warn", TOOL, f"snapshot failed: {e}")
        return None
    _busy_prev = data.get("busy_prev")
    return data


def make_smart(seed=None):
    """Предиктивный контроллер из presets.smart (см. fanpult/phase.py)."""
    if fanlib is None:
        return None
    try:
        return fanlib.Smart(preset() or None, seed=seed)
    except Exception as e:  # noqa: BLE001
        vlog.log("warn", TOOL, f"smart init failed: {e}")
        return None


def probe_access(timeout: float = 4.0) -> str:
    """Вердикт по правам на запись: direct | sudo | need-password | ..."""
    global _access
    if fanlib is None:
        _access = "no-vertil"
        return _access
    fans = _fans_obj()
    if fans is None or not fans.available:
        _access = "no-hwmon"
        return _access
    if fans.writable or os.geteuid() == 0:
        _access = "direct"
        return _access
    # проверяем не `sudo true`, а реальную запись: NOPASSWD-правило на
    # victus-kbd даёт проход и status тоже (напрямую юзеру он не доступен)
    wrapper = _wrapper()
    probe = (["sudo", "-n", wrapper, "fans", "status"] if wrapper
             else ["sudo", "-n", "true"])
    try:
        proc = subprocess.run(
            probe,
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        vlog.log("warn", TOOL, f"sudo probe failed: {e}")
        _access = "error"
        return _access
    text = (proc.stderr or "").lower()
    if proc.returncode == 0:
        _access = "sudo"
    elif "password" in text or "пароль" in text:
        _access = "need-password"
    else:
        _access = "error"
    return _access


def access() -> str | None:
    return _access


def _needs_priv() -> bool:
    if fanlib is None or os.geteuid() == 0:
        return False
    fans = _fans_obj()
    return not (fans is not None and fans.writable)


def _wrapper() -> str | None:
    """NOPASSWD-бинарник из README: права на запись уже выданы ему в sudoers,
    поэтому `sudo -n victus-kbd fans …` работает без пароля."""
    if os.path.isfile(KBD) and os.access(KBD, os.X_OK):
        return KBD
    return None


def _argv(*args: str) -> list:
    args = [str(a) for a in args]
    if not _needs_priv():
        return [sys.executable, FANCTL, *args]
    wrapper = _wrapper()
    if wrapper:
        return ["sudo", "-n", wrapper, "fans", *args]
    # правила нет/бинарник не найден — последний шанс: sudo сам спросит пароль
    return ["sudo", "-n", sys.executable, FANCTL, *args]


def call_sync(*args: str, timeout: float = 6.0) -> tuple[bool, str]:
    """Одна команда fanctl. (ok, текст ответа/ошибки)."""
    global _access
    try:
        proc = subprocess.run(
            _argv(*args),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError as e:
        return False, str(e)
    text = ((proc.stderr or proc.stdout or "").strip()
            or f"rc={proc.returncode}")
    if proc.returncode != 0:
        low = text.lower()
        if "password" in low or "пароль" in low:
            _access = "need-password"
        elif "hp hwmon" in low:
            _access = "no-hwmon"
        vlog.log("warn", TOOL, f"fanctl {' '.join(args)} rc={proc.returncode}: {text}")
        return False, text
    return True, (proc.stdout or "").strip()


async def call(*args: str, timeout: float = 6.0) -> tuple[bool, str]:
    """То же асинхронно — чтобы запись не тормозила цикл Textual."""
    return await asyncio.to_thread(call_sync, *args, timeout=timeout)


def shutdown() -> str:
    """Выход TUI: если мы управляли вентиляторами и режим ещё MANUAL —
    держим безопасный PWM (guard.sh: контроллер умер -> hold 180)."""
    msg = ""
    try:
        if session["controlled"]:
            fans = _fans_obj()
            mode = (fans.read() or {}).get("mode") if fans else None
            if mode == 1:
                level = hold_pwm()
                ok, err = call_sync("hold", str(level), timeout=4.0)
                msg = f"hold pwm={level} (mode=1)" if ok else f"hold failed: {err}"
                if ok:
                    vlog.log_info(TOOL, msg)
                else:
                    vlog.log("warn", TOOL, msg)
    finally:
        session["controlled"] = False
        session["autopilot"] = False
    return msg
