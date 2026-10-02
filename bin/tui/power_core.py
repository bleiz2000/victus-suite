"""power_core — режимы питания victus-suite, пользовательская часть.

Делает только то, что доступно без root: профиль power-profiles-daemon,
герцовка панели (hyprctl), вентиляторы через NOPASSWD-хелпер victus-kbd.
Всё, что требует прав, уходит в bin/victus-power — узкий белый-лист
подкоманд, никакой оболочки и произвольных путей.

Заимствовано архитектурно у Omen Space (профиль питания + ACPI/WMI-ручки),
код не форк: свой минималистичный слой поверх своей TUI.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from tui import core

TOOL = "power_core"

_BIN = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))  # bin/
KBD = os.path.join(_BIN, "victus-kbd")
POWER = os.path.join(_BIN, "victus-power")
PREV_FILE = os.path.join(os.path.dirname(core.STATE_FILE), "power_prev.json")

# «Печатная машинка»: желаемое состояние без root
TARGET_PPD = "power-saver"
TARGET_HZ_MAX = 60          # ниже не опускаемся: глаза важнее автономности
FAN_QUIET_MODE = "2"        # pwm1_enable=2 → тихая BIOS-кривая


def run(argv, timeout=8.0):
    """(rc, stdout, stderr); rc=None — бинарник не найден/не запустился."""
    if not argv or not shutil.which(argv[0]):
        return None, "", "нет %s" % (argv[0] if argv else "?")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _json(argv, timeout=8.0):
    rc, out, err = run(argv, timeout)
    if rc != 0:
        return None, err.strip() or out.strip() or "rc=%s" % rc
    try:
        return json.loads(out), ""
    except ValueError:
        return None, "не JSON: %s" % out.strip()[:120]


# ------------------------------------------------------------------ железо
def monitors():
    data, _ = _json(["hyprctl", "monitors", "-j"])
    return data if isinstance(data, list) else []


def monitor_info():
    """{name,w,h,hz,x,y,scale,modes:[...],available:[hz...]} быстрого экрана."""
    ms = monitors()
    if not ms:
        return None
    m = max(ms, key=lambda d: float(d.get("refreshRate") or 0))
    modes = [str(x) for x in (m.get("availableModes") or [])]
    avail = []
    for mode in modes:
        try:
            avail.append(float(mode.rsplit("@", 1)[1].rstrip("Hz")))
        except (ValueError, IndexError):
            pass
    return {
        "name": m.get("name"),
        "w": int(m.get("width") or 0),
        "h": int(m.get("height") or 0),
        "hz": round(float(m.get("refreshRate") or 0), 2),
        "x": int(m.get("x") or 0),
        "y": int(m.get("y") or 0),
        "scale": float(m.get("scale") or 1),
        "modes": modes,
        "available": sorted(set(avail)),
    }


def set_refresh(mon: dict, hz: float) -> bool:
    """Переключить герцовку панели и ПРОВЕРИТЬ результат.

    hyprctl keyword monitor в текущей сборке Hyprland возвращает rc=0, но
    печатает «keyword can't work with non-legacy parsers» и ничего не меняет —
    поэтому рабочий путь идёт через wlr-randr (zwlr_output_management), а
    hyprctl остаётся запасным вариантом.
    """
    if not mon or not mon.get("name"):
        return False
    mode = None
    for candidate in mon.get("modes") or []:
        try:
            cand_hz = float(candidate.rsplit("@", 1)[1].rstrip("Hz"))
        except (ValueError, IndexError):
            continue
        if abs(cand_hz - hz) <= 0.5:
            mode = candidate
            break
    if mode is None:
        mode = "%dx%d@%.3f" % (mon["w"], mon["h"], hz)

    if shutil.which("wlr-randr"):
        rc, _o, _e = run(["wlr-randr", "--output", mon["name"], "--mode", mode])
        if rc == 0 and _refresh_ok(mon["name"], hz):
            return True
    # запасной путь (старые Hyprland)
    spec = "%s,%dx%d@%.2f,%dx%d,%s" % (
        mon["name"], mon["w"], mon["h"], hz, mon["x"], mon["y"], mon["scale"])
    run(["hyprctl", "keyword", "monitor", spec])
    return _refresh_ok(mon["name"], hz)


def _refresh_ok(name: str, hz: float, wait: float = 1.5) -> bool:
    """Композитор применяет режим не мгновенно — дождаться и сверить."""
    end = time.monotonic() + wait
    while True:
        for m in monitors():
            if m.get("name") == name and abs(
                    float(m.get("refreshRate") or 0) - hz) <= 1.0:
                return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.3)


def ppd_get() -> str | None:
    rc, out, _err = run(["powerprofilesctl", "get"])
    return out.strip() if rc == 0 and out.strip() else None


def ppd_set(name: str) -> bool:
    rc, _o, _e = run(["powerprofilesctl", "set", name])
    return rc == 0


def battery() -> dict:
    base = "/sys/class/power_supply"
    info = {"present": False}
    try:
        entries = os.listdir(base)
    except OSError:
        return info
    for name in entries:
        if not name.startswith("BAT"):
            continue
        d = os.path.join(base, name)
        info["present"] = True
        for key, fn in (("status", "status"), ("capacity", "capacity")):
            try:
                with open(os.path.join(d, fn)) as fh:
                    info[key] = fh.read().strip()
            except OSError:
                pass
        break
    return info


def fan_status() -> dict | None:
    """Снимок вентиляторов через NOPASSWD-хелпер (JSON из fanctl status)."""
    rc, out, _err = run(["sudo", "-n", KBD, "fans", "status"])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def root_status() -> dict | None:
    data, _err = _json(["sudo", "-n", POWER, "status", "--json"])
    return data if isinstance(data, dict) else None


# -------------------------------------------------------------- переключение
def _load_prev():
    try:
        with open(PREV_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_prev(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(PREV_FILE), exist_ok=True)
        with open(PREV_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _step(res: dict, name: str, ok: bool, detail: str = "") -> None:
    (res["applied"] if ok else res["failed"]).append(
        "%s%s" % (name, (" — " + detail) if detail else ""))


def set_typewriter(on: bool) -> dict:
    """Включить/выключить ультра-режим. Возвращает {applied, failed, skipped}."""
    res = {"mode": "typewriter" if on else "normal",
           "applied": [], "failed": [], "skipped": []}

    if on:
        # Точка отката — состояние ДО первого включения. Снимок в корне
        # берём ЗДЕСЬ, до PPD: сам PPD пишет platform_profile и EPP, и если
        # снимать позже, в откат попадает уже «печатная машинка».
        if not os.path.exists(PREV_FILE):
            _save_prev({"ppd": ppd_get(), "monitor": monitor_info(),
                        "fans": (fan_status() or {}).get("mode"),
                        "ppd_done": False})
            data, err = _json(["sudo", "-n", POWER, "snapshot", "--json"])
            if data is None:
                _step(res, "точка отката", False, err)
            elif data.get("failed"):
                # хелпер отказался: снимок уже есть или система уже изменена.
                # Это НЕ успех — без честного baseline откат будет врать.
                _step(res, "точка отката", False, data["failed"][0])
            else:
                _step(res, "точка отката сохранена"
                      if not data.get("skipped") else data["skipped"][0], True)
    prev = _load_prev() or {}

    # ПОРЯВОК ВАЖЕН: запись platform_profile (в т.ч. через power-profiles-daemon)
    # заставляет EC прошить свои лимиты и сбросить RAPL PL1 обратно на 55 Вт.
    # Поэтому root-часть (RAPL и всё остальное) выполняется ПОСЛЕДНЕЙ.

    # --- 1. профиль питания PPD (без root) ---------------------------------
    want = TARGET_PPD if on else (prev.get("ppd") or "balanced")
    if ppd_get() is None:
        res["skipped"].append("power-profiles-daemon не найден")
    elif ppd_set(want):
        _step(res, "PPD→%s" % want, True)
        if on:
            prev["ppd_done"] = True
    else:
        _step(res, "PPD→%s" % want, False)

    # --- 2. герцовка панели -------------------------------------------------
    mon = monitor_info()
    if mon is None:
        res["skipped"].append("нет hyprctl/монитора")
    else:
        avail = [h for h in (mon["available"] or []) if h > 0] or [mon["hz"]]
        if on:
            target = min(min(avail), TARGET_HZ_MAX)
            _step(res, "Герцовка→%s Гц" % _fmt(target), set_refresh(mon, target))
        else:
            saved = (prev.get("monitor") or {}).get("hz")
            if not saved:
                res["skipped"].append("герцовка: прошлое значение не сохранено")
            else:
                _step(res, "Герцовка→%s Гц" % _fmt(saved),
                      set_refresh(mon, saved))

    # --- 3. тихие вентиляторы (BIOS-кривая = пассивный режим на простое) ----
    # при выключении возвращаем прежний режим, а не оставляем тихий:
    # ТЗ требует полного отката, а «AUTO» — это тоже изменение.
    fan_mode = FAN_QUIET_MODE if on else str(prev.get("fans") or FAN_QUIET_MODE)
    rc, out, err = run(["sudo", "-n", KBD, "fans", "set-mode", fan_mode])
    if rc == 0:
        _step(res, "Вентиляторы→%s (BIOS AUTO)" % ("тихо" if on else "прежний режим")
              if fan_mode == FAN_QUIET_MODE else
              "Вентиляторы→режим %s" % fan_mode, True)
    else:
        _step(res, "Вентиляторы→режим %s" % fan_mode, False,
              (err or out).strip()[:80])

    # --- 4. root-часть: частоты, turbo, RAPL, дискретка, MUX (последней) ----
    # щедрый таймаут: хелпер ждёт ухода дискретки в Runtime D3 и ретраит
    # частотные ручки (intel_pstate не берёт запись с первого раза)
    args = ["apply", "typewriter"] if on else ["restore"]
    data, err = _json(["sudo", "-n", POWER] + args + ["--json"], timeout=45.0)
    if data is None:
        _step(res, "victus-power %s" % args[0], False, err)
    else:
        res["applied"].extend(data.get("applied") or [])
        res["failed"].extend(data.get("failed") or [])
        res["skipped"].extend(data.get("skipped") or [])

    if on:
        _save_prev(prev)
    elif not res["failed"]:
        # Прошлую точку стираем только после ЧИСТНОГО отката: если корневой
        # снимок потерялся, ppd/герцовка в файле — единственные оставшиеся
        # следы baseline.
        try:
            os.remove(PREV_FILE)
        except OSError:
            pass

    res["status"] = status()
    return res


def _fmt(hz) -> str:
    return str(int(hz)) if abs(hz - round(hz)) < 0.05 else ("%.1f" % hz)


# Режим считаем ПО ЖЕЛЕЗУ, а не по файлу состояния TUI: состояние на диске
# врёт после сбоя, ручного `victus-power restore` или частичного apply.
MODE_NORMAL = "normal"
MODE_TYPEWRITER = "typewriter"
MODE_PARTIAL = "partial"


def mode(root: dict | None) -> str:
    """Реальный режим системы.

    normal     — точка отката отсутствует: режима нет
    typewriter — точка отката есть И жёсткие ручки действительно утоплены
    partial    — точка отката есть, но часть ручков вернулась (прошивка
                 перетёрла RAPL, apply оборвался) — UI обязан это показать
    """
    if root is None:
        # sudo недоступен: единственный ориентир — пользовательская точка
        return MODE_TYPEWRITER if _load_prev() else MODE_NORMAL
    if not root.get("typewriter_saved"):
        return MODE_NORMAL
    turbo_off = str(root.get("no_turbo")) == "1"
    try:
        pl1 = float(root.get("rapl_pl1_w") or 99)
    except (TypeError, ValueError):
        pl1 = 99.0
    return MODE_TYPEWRITER if (turbo_off and pl1 <= 20.0) else MODE_PARTIAL


def is_active() -> bool:
    """Режим включён? По root-снимку (он появляется только при apply)."""
    root = root_status()
    if root is not None:
        return bool(root.get("typewriter_saved"))
    return bool(_load_prev())


def status() -> dict:
    """Сводка для вкладки «Питание». Части, которых нет, просто отсутствуют."""
    st = {"battery": battery()}
    st["ppd"] = ppd_get()
    st["monitor"] = monitor_info()
    st["fans"] = fan_status()
    root = root_status()
    st["root"] = root
    st["root_ok"] = root is not None
    st["mode"] = mode(root)
    st["typewriter"] = st["mode"] != MODE_NORMAL
    return st
