"""power_core — режимы питания victus-suite, пользовательская часть.

Делает только то, что доступно без root: профиль power-profiles-daemon,
герцовка панели (hyprctl), вентиляторы через NOPASSWD-хелпер victus-kbd.
Всё, что требует прав, уходит в bin/victus-power — узкий белый-лист
подкоманд, никакой оболочки и произвольных путей.

Заимствовано архитектурно у Omen Space (профиль питания + ACPI/WMI-ручки),
код не форк: свой минималистичный слой поверх своей TUI.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

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
    """(данные, ошибка). stdout разбирается ПЕРЕД проверкой кода возврата.

    victus-power отдаёт rc=1 вместе с валидным JSON, когда сам честно
    сообщил об ошибке (отказ снимать baseline, частичный apply). Если
    сначала смотреть на rc, вызывающий код получит килобайт JSON вместо
    смысла — так в статусе и появилась строка
    «failed: точка отката — {"mode": "snapshot", …}».
    """
    rc, out, err = run(argv, timeout)
    try:
        return json.loads(out), ""
    except ValueError:
        pass
    if rc != 0:
        return None, err.strip() or out.strip() or "rc=%s" % rc
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
        # ГОТОВЫЙ mode из Hyprland («1920x1080@60.00Hz») wlr-randr отвергает:
        # у панели rate 60.004002, а не 60.00. Точный режим достаём сами.
        exact = _wlr_mode_name(mon["name"], hz) or mode
        rc, _o, _e = run(["wlr-randr", "--output", mon["name"], "--mode", exact])
        if rc == 0 and _refresh_ok(mon["name"], hz):
            return True
    # запасной путь (старые Hyprland)
    spec = "%s,%dx%d@%.2f,%dx%d,%s" % (
        mon["name"], mon["w"], mon["h"], hz, mon["x"], mon["y"], mon["scale"])
    run(["hyprctl", "keyword", "monitor", spec])
    return _refresh_ok(mon["name"], hz)


def _wlr_mode_name(name: str, hz: float) -> str | None:
    """Точный режим из вывода wlr-randr: «1920x1080 px, 60.004002 Hz».

    Строка mode из Hyprland округлена (60.00Hz), а wlr-randr сверяет её с
    EDID-таймингом и печатает «unknown mode» — из-за этого сброс герцовки
    на 60 Гц молча не применялся и подсказка врала про 60 при реальных 144.
    """
    rc, out, _e = run(["wlr-randr", "--output", name])
    if rc != 0:
        return None
    best, best_d = None, 1e9
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)x(\d+) px, ([\d.]+) Hz", line)
        if not m:
            continue
        d = abs(float(m.group(3)) - float(hz))
        if d < best_d:
            best = "%sx%s@%s" % (m.group(1), m.group(2), m.group(3))
            best_d = d
    return best if best_d <= 1.0 else None

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


def _num(info: dict, key: str, scale: float):
    """Число из sysfs-файла питания (µWh/µW/µA/µV → базовые единицы)."""
    try:
        return float(str(info.get(key) or "").split()[0]) / scale
    except (ValueError, TypeError, IndexError):
        return None


_ENERGY_CACHE: dict = {}
_POWER_EMA: dict = {"w": None, "t": 0.0}


def _smooth_power(w: float | None) -> float | None:
    """Сглаженная мгновенная мощность: EMA по power_now.

    Сырой power_now промежен и ступенчат (обновляется ~1 раз в секунду,
    шаг ~0.55 Вт, отстаёт на 1–3 с) — в подсказке он выглядит «кривым».
    Скользящее среднее с α=0.5 убирает ступеньки, но всё ещё реагирует
    на ползунок за пару секунд.
    """
    if w is None:
        return _POWER_EMA.get("w")
    prev = _POWER_EMA.get("w")
    now = time.monotonic()
    # после паузы в опросе (спящий режим) старое значение не тянем
    if prev is None or now - _POWER_EMA.get("t", 0.0) > 30:
        val = w
    else:
        val = prev + 0.5 * (w - prev)
    _POWER_EMA.update(w=round(val, 2), t=now)
    return _POWER_EMA["w"]


def _avg_watts(wh: float | None) -> float | None:
    """Средняя мощность из падения energy_now за последние 12..600 с."""
    now = time.monotonic()
    prev_wh = _ENERGY_CACHE.get("wh")
    if wh is None:
        return _ENERGY_CACHE.get("avg")
    if prev_wh is None or now - _ENERGY_CACHE.get("t", 0) < 12:
        # первый замер или интервал ещё короткий — держим прежнюю цифру,
        # иначе она прыгала бы на каждом тике и «лгала» бы ещё больше
        _ENERGY_CACHE.update(wh=wh, t=now)
        return _ENERGY_CACHE.get("avg")
    dt = now - _ENERGY_CACHE["t"]
    _ENERGY_CACHE.update(wh=wh, t=now)
    if dt > 600 or prev_wh <= wh:
        return _ENERGY_CACHE.get("avg")          # спящий режим / зарядка
    _ENERGY_CACHE["avg"] = round((prev_wh - wh) / (dt / 3600.0), 1)
    return _ENERGY_CACHE["avg"]


def battery() -> dict:
    """Заряд + сколько он продержит при ТЕКУЩЕМ расходе.

    Оценка честная и живая: fuel-gauge отдаёт energy_now и мгновенную
    мощность, поэтому цифра сама подстраивается под нагрузку — браузер,
    сборка, звук. Это ровно ответ на «сколько продержит на этом режиме»,
    только измеренный, а не придуманный.
    """
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
        for key in ("status", "capacity", "energy_now", "energy_full",
                    "power_now", "current_now", "voltage_now"):
            try:
                with open(os.path.join(d, key)) as fh:
                    info[key] = fh.read().strip()
            except OSError:
                pass
        break

    wh = _num(info, "energy_now", 1e6)              # µWh → Вт·ч
    full = _num(info, "energy_full", 1e6)
    w = _num(info, "power_now", 1e6)                # µW → Вт
    if not w:
        cur, vol = _num(info, "current_now", 1e6), _num(info, "voltage_now", 1e6)
        if cur and vol:
            w = cur * vol                            # fallback: A × V
    info["watts"] = round(w, 1) if w else None
    info["w_inst"] = _smooth_power(info["watts"])
    # ЭС показывает `power_now` с большой задержкой и ступенями (замерено:
    # 19.5 Вт → 25 Вт уже ПОСЛЕ снятия нагрузки). Поэтому рядом держим
    # среднее по падению энергии — честное, но медленное.
    info["avg_w"] = _avg_watts(wh)

    status = (info.get("status") or "").lower()
    hours = None
    if wh and w and w > 0:
        # оценку держим на худшем из двух: сырые ступени ЭС врём вниз,
        # длинное среднее по энергии — вверх (память на прошлую нагрузку)
        used = max(w, info.get("w_inst") or 0.0, info.get("avg_w") or 0.0)
        if used > 0:
            if "discharg" in status:
                hours = wh / used                    # сколько ещё хватит
            elif "charg" in status and full:
                hours = max(0.0, full - wh) / used   # сколько до полного
    info["hours"] = round(hours, 2) if hours and hours > 0.02 else None
    return info


def cpu_w() -> float | None:
    """Мгновенная мощность пакета CPU (RAPL, интервал ~1.2 с).

    Единственная цифра, которая реагирует на ползунок потолка сразу:
    батарейный `power_now` отстаёт на секунды и двигается ступенями.
    """
    # 0.8 с: RAPL считает в µJ, за 0.8 с на 5 Вт накапливается ~4·10⁶ µJ —
    # точности хватает, а сводка статуса экономит 0.4 с на каждом тике
    data, _err = _json(["sudo", "-n", POWER, "draw", "--dur", "0.8", "--json"],
                       timeout=12.0)
    if data is None:
        return None
    val = data.get("cpu_w")
    try:
        return round(float(val), 1)
    except (TypeError, ValueError):
        return None


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


def set_watt_limit(watt: int) -> dict:
    """Потолок мощности CPU 5..25 Вт. Работает только при включённой
    «печатной машинке» — корень сам откажет, если режим выключен."""
    res = {"mode": "watts", "applied": [], "failed": [], "skipped": []}
    try:
        watt = int(watt)
    except (TypeError, ValueError) as exc:
        res["failed"].append("watts: %s" % exc)
        return res
    data, err = _json(["sudo", "-n", POWER, "watts", str(watt), "--json"],
                      timeout=20.0)
    if data is None:
        res["failed"].append(err or "victus-power watts")
    else:
        res["applied"] = data.get("applied") or []
        res["failed"] = data.get("failed") or []
        res["skipped"] = data.get("skipped") or []
    return res


def cascade_set(target: int, cpu: int | None = None,
                stabilize: bool = True, dur: float = 30.0) -> dict:
    """Каскад на цель по ВСЕМУ ноутбуку (TUI: 8/10/15/20/25; CLI: 5..25).

    Стабилизация (по умолчанию вкл): хелпер после применения меряет факт
    от батареи и стягивает бюджет CPU к цели.

    Окно замера 30 с не случайно: шкала energy_now на BAT1 шагает по
    10 мWh — на 8-секундном окне это квант 4.5 Вт (мы одно время «мерили»
    4.5 Вт там, где ноут тянет 9). На 30 с остаётся ~0.6 Вт неточности.
    Вызов занимает до ~70 с: спокойное окно до ужатий, а не мгновенный
    красивый ответ, которого система не смогла бы подтвердить.
    """
    argv = ["sudo", "-n", POWER, "cascade", str(int(target)), "--json"]
    if cpu is not None:
        argv += ["--cpu", str(int(cpu))]
    argv += (["--dur", str(float(dur))] if stabilize else ["--no-stabilize"])
    data, err = _json(argv, timeout=150.0)
    if data is None:
        return {"mode": "cascade", "applied": [], "failed": [err or "cascade"],
                "steps": []}
    return data


def phase(target: int, dur: float = 30.0) -> dict:
    """Одна фаза стабилизации: покой 4 с → замер → вердикт (без записи).

    Разделение нужно только ради честного таймера в интерфейсе: пока хелпер
    меряет, TUI показывает «Стабилизация: ~N с», а не молча висит. В ответе —
    measure (факт/плата/min_w/feasible) и next_cpu: на сколько ужать CPU,
    если цель не взята.
    """
    data, err = _json(["sudo", "-n", POWER, "phase",
                       "--target", str(int(target)), "--dur", str(float(dur)),
                       "--json"], timeout=180.0)
    return data if isinstance(data, dict) else {"mode": "phase",
                                                "failed": [err or "phase"]}


def measure(dur: float = 40.0) -> dict:
    """Честный замер потребления всей системы от батареи.

    40 с — минимум, на котором шкала energy_now успевает накопить ~10
    шагов и погрешность падает до ~0.5 Вт.
    """
    data, err = _json(["sudo", "-n", POWER, "measure", "--dur", str(dur),
                       "--json"], timeout=90.0)
    return data if isinstance(data, dict) else {"ok": False,
                                                "reason": err or "measure"}


def cascade_off() -> dict:
    data, err = _json(["sudo", "-n", POWER, "cascade-off", "--json"],
                      timeout=30.0)
    if data is None:
        return {"mode": "cascade-off", "applied": [], "failed": [err or "off"]}
    return data


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
    # Порог 30 Вт, а не 20: ползунок потолка мощности разрешает 5..25 Вт,
    # и «частично» на всех значениях выше 20 гасило бы его же самого.
    # Baseline — 55 Вт, поэтому 30 по-прежнему надёжно отличает режим.
    return MODE_TYPEWRITER if (turbo_off and pl1 <= 30.0) else MODE_PARTIAL


def is_active() -> bool:
    """Режим включён? По root-снимку (он появляется только при apply)."""
    root = root_status()
    if root is not None:
        return bool(root.get("typewriter_saved"))
    return bool(_load_prev())


def status() -> dict:
    """Сводка для вкладки «Питание». Части, которых нет, просто отсутствуют.

    Опросы независимы, поэтому идут параллельно: последовательно сводка
    собиралась 1.9 с (почти всё — окно RAPL), и вкладка отвечала с задержкой
    на каждый тик. Теперь — сумма максимального, ~1.4 с, и интерфейс
    остаётся отзывчивым (всё равно в фоновом потоке).
    """
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_bat = pool.submit(battery)
        f_cpu = pool.submit(cpu_w)
        f_ppd = pool.submit(ppd_get)
        f_mon = pool.submit(monitor_info)
        f_fan = pool.submit(fan_status)
        f_root = pool.submit(root_status)
        st = {"battery": f_bat.result(), "cpu_w": f_cpu.result()}
        st["ppd"] = f_ppd.result()
        st["monitor"] = f_mon.result()
        st["fans"] = f_fan.result()
        root = f_root.result()
    st["root"] = root
    st["root_ok"] = root is not None
    st["mode"] = mode(root)
    st["typewriter"] = st["mode"] != MODE_NORMAL

    # честная нижняя строка: сколько ноут тянет ПО ФАКТУ и из чего оно
    # складывается. `w_inst` — сглаженный power_now (батарея, ~1 с),
    # `avg_w` — среднее по падению энергии (стабильное, но медленное).
    bat = st["battery"] or {}
    status = (bat.get("status") or "").lower()
    st["on_ac"] = "discharg" not in status
    # Живая цифра — среднее по падению energy_now (окно ≥12 с): оно не
    # прыгает на ступенях промежённого power_now, поэтому нижняя строка
    # не «скачет до 14–15 Вт» на восьми измеренных. EMA остаётся только
    # запасным вариантом, пока первое окно ещё не накопилось.
    raw = bat.get("w_inst") or bat.get("watts")
    if st["on_ac"]:
        raw = None                       # на зарядке это ток зарядки, не расход
    avg = None if st["on_ac"] else (bat.get("avg_w") or raw)
    st["total_w"] = avg
    st["total_inst_w"] = raw
    st["total_avg_w"] = avg
    cpu = st.get("cpu_w")
    # плату считаем от МГНОВЕННОЙ цифры: cpu — это текущий RAPL, вычитать
    # из него среднее за 12 с нельзя (получится искажённая «плата»)
    base = raw if raw is not None else avg
    st["platform_w"] = (round(base - cpu, 1)
                        if base is not None and cpu is not None else None)
    # план каскада из корневого статуса (цель, ожидание, минимум, замер)
    plan = (root or {}).get("cascade_plan") or {}
    st["target"] = (root or {}).get("cascade_target")
    st["expect_w"] = plan.get("expect_w")
    st["min_w"] = plan.get("min_w")
    st["feasible"] = plan.get("feasible")
    st["measure"] = (root or {}).get("cascade_measure")
    st["brightness_pct"] = (root or {}).get("brightness_pct")
    return st
