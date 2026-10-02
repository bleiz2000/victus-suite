#!/usr/bin/env python3
"""fanlib — общий слой для пульта, тестов и контроллеров вентиляторов HP Victus.

Единственный источник истины по настройкам: vertil/config/presets.json.
Никаких зависимостей кроме stdlib; ничего не пишет в систему.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CONFIG = os.path.join(ROOT, "config", "presets.json")

PWM_MAX = 255


# --------------------------------------------------------------------------- #
# пресет
# --------------------------------------------------------------------------- #
def load_preset(path: str | None = None) -> dict:
    with open(path or CONFIG, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_preset(preset: dict, path: str | None = None) -> None:
    p = path or CONFIG
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(preset, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p)


def emit_env(preset: dict | None = None) -> str:
    """Плоский .env, чтобы bash-инструменты (guard/loadgen) читали тот же пресет."""
    p = preset or load_preset()
    g, s, b, lg = p["guard"], p["smart"], p["brutal"], p["loadgen"]
    rows = [
        ("PRESET_NAME", p.get("name", "")),
        ("GUARD_CPU_HOT", g["cpu_hot_c"]),
        ("GUARD_CPU_STREAK", g["cpu_hot_streak"]),
        ("GUARD_GPU_HOT", g["gpu_hot_c"]),
        ("GUARD_HOLD_PWM", g["hold_pwm"]),
        ("GUARD_POLL_S", g["poll_s"]),
        ("SMART_FLOOR", s["floor_pwm"]),
        ("SMART_CEIL", s["ceil_pwm"]),
        ("SMART_RISE", s["rise_pwm_per_s"]),
        ("SMART_FALL", s["fall_pwm_per_s"]),
        ("SMART_EMERG_CPU", s["emergency"]["cpu_c"]),
        ("SMART_EMERG_GPU", s["emergency"]["gpu_c"]),
        ("SMART_CPU_CAP", s["caps"]["cpu_pwm_max"]),
        ("SMART_GPU_CAP", s["caps"]["gpu_pwm_max"]),
        ("BRUTAL_CPU_ON", b["cpu_on_c"]),
        ("BRUTAL_GPU_ON", b["gpu_on_c"]),
        ("BRUTAL_CPU_OFF", b["cpu_off_c"]),
        ("BRUTAL_GPU_OFF", b["gpu_off_c"]),
        ("BRUTAL_BASE", b["base_pwm"]),
        ("LOADGEN_YIELD_CPU", lg["yield"]["cpu_c"]),
        ("LOADGEN_LIGHT_CPU", lg["light"]["cpu_c"]),
        ("FAN_MAX_RPM", p["device"]["max_cpu_rpm"]),
    ]
    lines = ["# generated from config/presets.json — не редактировать вручную",
             "# regenerate: python3 tools/fanlib.py --emit-env"]
    lines += ["%s=%s" % (k, v) for k, v in rows]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# поиск чипов (по name, индекс hwmon плавает)
# --------------------------------------------------------------------------- #
def find_hwmon(chip: str, need: str | None = None) -> str | None:
    base = "/sys/class/hwmon"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None
    for n in names:
        d = os.path.join(base, n)
        try:
            with open(os.path.join(d, "name"), "r") as fh:
                if fh.read().strip() != chip:
                    continue
        except OSError:
            continue
        if need and not os.path.exists(os.path.join(d, need)):
            continue
        return d
    return None


def _read(path: str):
    try:
        with open(path, "r") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _int(path: str):
    v = _read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# вентиляторы
# --------------------------------------------------------------------------- #
class Fans:
    """Обёртка над hp-wmi: режимы, запись PWM, текущие обороты."""

    def __init__(self, preset: dict | None = None):
        self.preset = preset or load_preset()
        f = self.preset["fans"]
        self.hp = find_hwmon(self.preset["sensors"]["fan_chip"], "pwm1")
        self.cpu_rpm_in, self.gpu_rpm_in = f["cpu"]["rpm_in"], f["gpu"]["rpm_in"]
        self.cpu_pwm_out = f["cpu"]["pwm_out"]
        gpu_pwm = f["gpu"]["pwm_out"]
        # Драйвер может не экспортировать второй канал (Omen Space hp-wmi:
        # is_visible(channel=1) -> 0, pwm2 физически нет, обе лопасти ведёт
        # один pwm1). Тогда НЕ пытаемся писать в несуществующий файл —
        # open(..., "w") в sysfs вернул бы EACCES и мы соврали бы про права.
        self.gpu_pwm_out = (
            gpu_pwm if self.hp and os.path.exists(os.path.join(self.hp, gpu_pwm))
            else None
        )
        self.shared_pwm = self.gpu_pwm_out is None
        self.enable_attr = f["enable_attr"]
        self.modes = {int(v): k for k, v in f["modes"].items()}
        self.pwm_max = f["pwm_max"]

    # -- состояние ---------------------------------------------------------- #
    @property
    def available(self) -> bool:
        return self.hp is not None

    @property
    def channels(self) -> int:
        """1 — один PWM на обе лопасти, 2 — независимые каналы."""
        return 1 if self.shared_pwm else 2

    @property
    def writable(self) -> bool:
        """Можно ли реально писать: атрибут существует И доступен на запись."""
        if not self.hp:
            return False
        paths = [os.path.join(self.hp, self.enable_attr),
                 os.path.join(self.hp, self.cpu_pwm_out)]
        if self.gpu_pwm_out:
            paths.append(os.path.join(self.hp, self.gpu_pwm_out))
        return all(os.path.exists(p) and os.access(p, os.W_OK) for p in paths)

    def read(self) -> dict:
        if not self.hp:
            return {"mode": None, "mode_name": "N/A", "fan1": None, "fan2": None,
                    "pwm1": None, "pwm2": None, "pwm_shared": self.shared_pwm,
                    "channels": self.channels}
        mode = _int(os.path.join(self.hp, self.enable_attr))
        pwm1 = _int(os.path.join(self.hp, self.cpu_pwm_out))
        if self.shared_pwm:
            # один канал: driver ведёт обе лопасти от pwm1 (вторая с gpu_delta)
            pwm2 = pwm1
        else:
            pwm2 = _int(os.path.join(self.hp, self.gpu_pwm_out))
        return {
            "mode": mode,
            "mode_name": self.modes.get(mode, str(mode)),
            "fan1": _int(os.path.join(self.hp, self.cpu_rpm_in)),
            "fan2": _int(os.path.join(self.hp, self.gpu_rpm_in)),
            "pwm1": pwm1,
            "pwm2": pwm2,
            "pwm_shared": self.shared_pwm,
            "channels": self.channels,
        }

    # -- запись ------------------------------------------------------------- #
    def _w(self, attr: str, value: int) -> str | None:
        if not self.hp:
            return "hp hwmon not found"
        path = os.path.join(self.hp, attr)
        # Проверяем ДО open: на отсутствующем sysfs-файле open("w") просит
        # VFS создать узел, тот отвечает EACCES, и Python поднимает
        # PermissionError — то самое ложное «нет прав: нужен root».
        if not os.path.exists(path):
            return "нет атрибута %s — драйвер не экспортирует его (%s)" % (attr, path)
        try:
            with open(path, "w") as fh:
                fh.write("%d\n" % int(value))
        except FileNotFoundError:
            return "нет атрибута %s — драйвер не экспортирует его (%s)" % (attr, path)
        except PermissionError:
            return "нет прав: нужен root (sudo)"
        except OSError as e:
            return "%s (%s)" % (e, path)
        return None

    def enter_manual(self) -> str | None:
        """Вход в MANUAL. Не даёт скачка оборотов — драйвер снапшотит."""
        if (self.read() or {}).get("mode") == 1:
            return None
        return self._w(self.enable_attr, 1)

    def set_mode(self, mode: int) -> str | None:
        return self._w(self.enable_attr, mode)

    def set_pwm(self, p1: int, p2: int) -> str | None:
        """Мгновенная установка. Требует mode==1, иначе драйвер вернёт -EINVAL."""
        cur = (self.read() or {}).get("mode")
        if cur != 1:
            err = self.enter_manual()
            if err:
                return err
        p1 = max(0, min(self.pwm_max, int(p1)))
        p2 = max(0, min(self.pwm_max, int(p2)))
        if self.shared_pwm:
            # Один канал на обе лопасти: пишем максимум из двух требований,
            # иначе перегрев по «чужому» датчику (GPU при холодном CPU) был
            # бы молча отброшен.
            return self._w(self.cpu_pwm_out, max(p1, p2))
        for attr, val in ((self.cpu_pwm_out, p1), (self.gpu_pwm_out, p2)):
            err = self._w(attr, val)
            if err:
                return err
        return None

    def rpm_to_pwm(self, rpm: float) -> int:
        return max(0, min(self.pwm_max, int(round(rpm / self.preset["device"]["max_cpu_rpm"]
                                                   * self.pwm_max))))


# --------------------------------------------------------------------------- #
# датчики
# --------------------------------------------------------------------------- #
class RAPL:
    """Энергия пакета CPU через intel-rapl (нужен root: файл 0400)."""

    def __init__(self, zone: str = "intel-rapl:0"):
        self.path = "/sys/class/powercap/%s/energy_uj" % zone
        self._last = None

    def power(self) -> float | None:
        e = _int(self.path)
        now = time.monotonic()
        if e is None:
            self._last = None
            return None
        if self._last is None:
            self._last = (e, now)
            return None
        de, dt = e - self._last[0], now - self._last[1]
        self._last = (e, now)
        if dt <= 0 or de < 0:            # переполнение 64-битного счётчика
            return None
        return round(de / 1e6 / dt, 1)


class TempFilter:
    """Медиана-3 + ограничение скорости (slew) для одного датчика.

    ACPI-прокси VRM (TCPU_PCI) и coretemp иногда отдают одиночный скачок:
    такой всплеск давал крутой dT/dt, SMART экстраполировал его на горизонт
    и уходил в потолок — лопасти рвались на максимум без причины. Медиана
    выбрасывает одиночный выброс из окна (нужны 2 совпадения из 3), а
    slew-лимит ограничивает dT/dt, который видит экстраполяция. Настоящий
    разогрев проходит: он держится несколько снимков подряд.
    """

    def __init__(self, window: int = 3, rise: float | None = None,
                 fall: float | None = None):
        self.window = max(1, int(window))
        self.rise = None if rise is None else float(rise)   # °C за снимок
        self.fall = None if fall is None else float(fall)
        self.buf: list = []
        self.out: float | None = None

    def update(self, raw):
        if raw is None:
            # датчик мигнул — держим последнее валидное значение
            return self.out
        self.buf.append(float(raw))
        if len(self.buf) > self.window:
            self.buf.pop(0)
        med = sorted(self.buf)[len(self.buf) // 2]
        if self.out is None:
            self.out = round(med, 1)
            return self.out
        delta = med - self.out
        step = self.rise if delta > 0 else self.fall
        if step is not None:
            delta = max(-step, min(step, delta))
        self.out = round(self.out + delta, 1)
        return self.out

    def reset(self) -> None:
        self.buf.clear()
        self.out = None


class Sensors:
    """Один снимок всех величин, нужных пульту и контроллерам."""

    _NVIDIA = ("temperature.gpu", "utilization.gpu", "clocks.sm", "clocks.mem",
               "power.draw", "power.default_limit")

    def __init__(self, preset: dict | None = None):
        self.preset = preset or load_preset()
        sn = self.preset["sensors"]
        self.core = find_hwmon(sn["cpu_chip"], sn["cpu_input"])
        self.hp = find_hwmon(sn["fan_chip"], "fan1_input")
        self.rapl = RAPL()
        self.zone = "/sys/devices/virtual/thermal/%s/temp" % sn["vrm_proxy_zone"]
        self.thr_path = "/sys/devices/system/cpu/cpu0/thermal_throttle"
        self.fans = Fans(self.preset)
        self._nvidia_last_ok = True
        fp = (self.preset.get("smart") or {}).get("filter") or {}
        window = int(fp.get("median_window", 3))
        rise = float(fp.get("rise_c", 12.0))
        fall = float(fp.get("fall_c", 6.0))
        # VRM-канал — ACPI-прокси TCPU_PCI, он скачет и без нашей программы
        # (прошивка, соседняя линия питания). Ему собственное окно и свой
        # slew: медленнее и глубже, чем CPU/GPU/Board, чтобы микро-скачки
        # не доезжали ни до dT/dt, ни до кривой оборотов.
        vfp = fp.get("vrm") or {}
        vwin = int(vfp.get("median_window", 7))
        vrise = float(vfp.get("rise_c", 4.0))
        vfall = float(vfp.get("fall_c", 2.5))
        self._filt = {
            "t_cpu": TempFilter(window, rise, fall),
            "t_gpu": TempFilter(window, rise, fall),
            "t_board": TempFilter(window, rise, fall),
            "t_vrm": TempFilter(vwin, vrise, vfall),
        }

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _nvidia() -> dict:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=" + ",".join(Sensors._NVIDIA),
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3).stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            return {}
        if not out:
            return {}
        parts = [p.strip().rstrip("[W]") for p in out[0].split(",")]
        keys = ("t_gpu", "gpu_util", "sm", "mem", "gpu_w", "gpu_w_max")
        res = {}
        for k, v in zip(keys, parts):
            try:
                res[k] = round(float(v)) if k in ("sm", "mem") else float(v)
            except ValueError:
                res[k] = None
        return res

    @staticmethod
    def _freq() -> float | None:
        vals = []
        for i in range(16):
            v = _read("/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq" % i)
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        return round(sum(vals) / len(vals) / 1000.0) if vals else None

    @staticmethod
    def cpu_busy(prev=None, interval=1.0):
        """Доля активных потоков. prev=((idle,total), t) для дельты."""
        line = None
        with open("/proc/stat") as fh:
            for ln in fh:
                if ln.startswith("cpu "):
                    line = ln
                    break
        if not line:
            return 0.0, prev
        p = [int(x) for x in line.split()[1:]]
        idle = p[3] + (p[4] if len(p) > 4 else 0)
        total = sum(p)
        now = (idle, total, time.monotonic())
        if prev is None:
            return 0.0, now
        d_idle = now[0] - prev[0]
        d_tot = now[1] - prev[1]
        if d_tot <= 0:
            return 0.0, now
        return round((100.0 * (d_tot - d_idle)) / d_tot, 1), now

    # -- снимок ------------------------------------------------------------- #
    def read(self, busy_prev=None) -> dict:
        sn = self.preset["sensors"]
        d = {"t_cpu": None, "t_cpu_max": None, "t_vrm": None, "t_board": None,
             "t_gpu": None, "gpu_util": None, "gpu_w": None, "gpu_w_max": None,
             "sm": None, "mem": None, "cpu_w": None, "freq": None,
             "thr": None, "thr_ms": None, "cpu_busy": 0.0, "busy_prev": busy_prev}

        # CPU package + максимум по всем кристаллам coretemp
        if self.core:
            d["t_cpu"] = Sensors.mw_to_c(_int(os.path.join(self.core, sn["cpu_input"])))
            tmax = None
            try:
                for fn in sorted(os.listdir(self.core)):
                    if fn.startswith("temp") and fn.endswith("_input"):
                        v = _int(os.path.join(self.core, fn))
                        if v is not None and (tmax is None or v > tmax):
                            tmax = v
            except OSError:
                pass
            d["t_cpu_max"] = Sensors.mw_to_c(tmax)

        d["t_vrm"] = Sensors.mw_to_c(_int(self.zone))   # TCPU_PCI, прокси VRM
        board = find_hwmon(self.preset["sensors"]["board_proxy"])
        if board:
            d["t_board"] = Sensors.mw_to_c(_int(os.path.join(board, "temp1_input")))

        d.update(self._nvidia())
        d["cpu_w"] = self.rapl.power()
        d["freq"] = self._freq()

        for key, fn in (("thr", "package_throttle_count"),
                        ("thr_ms", "package_throttle_total_time_ms")):
            d[key] = _int(os.path.join(self.thr_path, fn))

        busy, d["busy_prev"] = self.cpu_busy(busy_prev)
        d["cpu_busy"] = busy
        d.update(self.fans.read())

        # Фильтрация: в t_* уходят сглаженные значения (ими управляет
        # контроллер), сырые копии остаются в *_raw — по ним считается
        # авария, чтобы фильтр не задержал реакцию на настоящий перегрев.
        for key, flt in self._filt.items():
            raw = d.get(key)
            d["%s_raw" % key] = raw
            d[key] = flt.update(raw)
        return d

    @staticmethod
    def mw_to_c(v):
        return None if v is None else round(v / 1000.0, 1)


# --------------------------------------------------------------------------- #
# контроллеры
# --------------------------------------------------------------------------- #
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class Brutal:
    """Bang-bang: 100% при пороге, база при остывании, иначе hold."""

    def __init__(self, preset: dict | None = None):
        b = (preset or load_preset())["brutal"]
        self.cpu_on, self.gpu_on = b["cpu_on_c"], b["gpu_on_c"]
        self.cpu_off, self.gpu_off = b["cpu_off_c"], b["gpu_off_c"]
        self.base, self.hot = b["base_pwm"], b["hot_pwm"]
        self.cur = self.base

    def update(self, s, dt):
        tc, tg = s["t_cpu"] or 0, s["t_gpu"] or 0
        if tc >= self.cpu_on or tg >= self.gpu_on:
            tgt, act = self.hot, "BRUTAL: hot -> 100%"
        elif tc <= self.cpu_off and tg <= self.gpu_off:
            tgt, act = self.base, "BRUTAL: cool -> base"
        else:
            tgt, act = self.cur, "BRUTAL: hold"
        changed = abs(tgt - self.cur) >= 1
        self.cur = tgt
        return int(tgt), int(tgt), act, changed


class Smart:
    """Предиктивное управление: экстраполяция dT/dt, пропорциональная полоса,
    двухскоростной slew-limit, приоритет VRM-канала, аварийный обход.

    Авария не прыгает в 100% мгновенно: один «горячий» снимок может быть
    всплеском (бурст браузера, индексация), поэтому вход в аварию требует
    EMERG_STREAK подряд горячих снимков, а сами вентиляторы разгоняются
    быстрым, но конечным темпом EMERG_RISE_MULT × rise_pwm_per_s.
    Это кодовое поведение, а не тюнинг: значения presets.smart не трогаются.
    """

    EMERG_STREAK = 2       # подряд «горячих» снимков (~2 с) до входа в аварию
    EMERG_RISE_MULT = 4    # темп разгона в аварии = rise_pwm_per_s × множитель

    def __init__(self, preset: dict | None = None, seed=None):
        p = (preset or load_preset())["smart"]
        self.p = p
        self.HORIZON = p["horizon_s"]
        self.FLOOR = p["floor_pwm"]
        self.CEIL = p["ceil_pwm"]
        self.RISE = p["rise_pwm_per_s"]
        self.FALL = p["fall_pwm_per_s"]
        self.DEADBAND = p["deadband"]
        self.win_cpu = p["slope_window_cpu_s"]
        self.win_vrm = p["slope_window_vrm_s"]
        self.keep = p["history_s"]
        self.c1 = p["cpu_band"]
        self.c2 = p["gpu_band"]
        self.c3 = p["vrm_band"]
        self.w_cg = p["weights"]["cpu_to_gpu"]
        self.w_vc = p["weights"]["vrm_to_cpu"]
        self.w_vg = p["weights"]["vrm_to_gpu"]
        self.e_cpu = p["emergency"]["cpu_c"]
        self.e_gpu = p["emergency"]["gpu_c"]
        hyst = p.get("hysteresis") or {}
        self.h_up = float(hyst.get("up", 0))
        self.h_down = float(hyst.get("down", 0))
        # гистерезис самой температуры VRM (до оценки полосы): ±1 °C дрожания
        # шумного TCPU_PCI не двигают score, пока отклонение не наберёт порог
        tvh = p.get("vrm_temp_hysteresis") or {}
        self.tv_up = float(tvh.get("up", 0))
        self.tv_down = float(tvh.get("down", 0))
        self.tv_h: float | None = None
        self.cap_cpu = p["caps"]["cpu_pwm_max"]
        self.cap_gpu = p["caps"]["gpu_pwm_max"]
        self.cap_over = p["caps"]["override_temp_c"]
        self.cap_on = bool(p["caps"].get("enabled", True))
        i1, i2 = p["init_pwm"]
        if seed:
            i1, i2 = seed
        self.p1, self.p2 = float(i1), float(i2)
        self.t1_h: float | None = None
        self.t2_h: float | None = None
        self.hist = []
        self._hot = 0
        self.written1 = self.written2 = None

    @staticmethod
    def _hyst(target: float, prev: float | None, up: float, down: float) -> float:
        """Гистерезис цели: вверх — только на up, вниз — только на down.

        Убирает дрожание вокруг границы полосы (цель то чуть выше, то чуть
        ниже → крутилка метётся), не трогая настоящие разогревы/остывания.
        """
        if prev is None:
            return target
        if target > prev + up:
            return target
        if target < prev - down:
            return target
        return prev

    @staticmethod
    def _slope(hist, idx, window):
        now = hist[-1][0]
        pts = [(h[0], h[idx]) for h in hist if now - h[0] <= window and h[idx] is not None]
        if len(pts) < 3:
            return 0.0
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        den = sum((p[0] - mx) ** 2 for p in pts)
        if den <= 0:
            return 0.0
        return sum((p[0] - mx) * (p[1] - my) for p in pts) / den

    def update(self, s, dt):
        now = time.monotonic()
        tc = s["t_cpu"] or 0.0
        tg = s["t_gpu"] or 0.0
        tv = s["t_vrm"] or 0.0
        # Гистерезис температуры VRM ДО истории и оценки: дрожание датчика
        # не двигает ни slope, ни score (up/down = 0 отключает, как раньше).
        tv = self._hyst(tv, self.tv_h, self.tv_up, self.tv_down)
        self.tv_h = tv
        self.hist.append((now, tc, tg, tv))
        self.hist = [h for h in self.hist if now - h[0] <= self.keep]

        dtc = self._slope(self.hist, 1, self.win_cpu)
        dtg = self._slope(self.hist, 2, self.win_cpu)
        dtv = self._slope(self.hist, 3, self.win_vrm)

        pc = tc + max(0.0, dtc) * self.HORIZON
        pg = tg + max(0.0, dtg) * self.HORIZON
        pv = tv + max(0.0, dtv) * self.HORIZON * 0.75

        score1 = max((pc - self.c1["low"]) / self.c1["span"],
                     self.w_vc * (pv - self.c3["low"]) / self.c3["span"])
        score2 = max((pg - self.c2["low"]) / self.c2["span"],
                     self.w_cg * (pc - self.c1["low"]) / self.c1["span"],
                     self.w_vg * (pv - self.c3["low"]) / self.c3["span"])

        t1 = self.FLOOR + (self.CEIL - self.FLOOR) * clamp(score1, 0.0, 1.0)
        t2 = self.FLOOR + (self.CEIL - self.FLOOR) * clamp(score2, 0.0, 1.0)
        t1 = self._hyst(t1, self.t1_h, self.h_up, self.h_down)
        t2 = self._hyst(t2, self.t2_h, self.h_up, self.h_down)
        self.t1_h, self.t2_h = t1, t2

        # авария: streak подряд горячих снимков, разгон быстрым темпом —
        # без мгновенного прыжка в 100 % (см. EMERG_STREAK/EMERG_RISE_MULT).
        # Порог сверяем и по сырым значениям: фильтр сглаживания не должен
        # откладывать реакцию на настоящий перегрев.
        tc_raw = s.get("t_cpu_raw")
        tg_raw = s.get("t_gpu_raw")
        hot = (max(tc, tc_raw if tc_raw is not None else tc) >= self.e_cpu
               or max(tg, tg_raw if tg_raw is not None else tg) >= self.e_gpu)
        self._hot = self._hot + 1 if hot else 0
        emerg = self._hot >= self.EMERG_STREAK
        step = dt if dt > 0 else 1.0
        if emerg:
            rise = self.RISE * self.EMERG_RISE_MULT * step
            self.p1 += clamp(self.CEIL - self.p1, -self.FALL * step, rise)
            self.p2 += clamp(self.CEIL - self.p2, -self.FALL * step, rise)
            self.p1 = clamp(self.p1, self.FLOOR, self.CEIL)
            self.p2 = clamp(self.p2, self.FLOOR, self.CEIL)
            act = "SMART: EMERGENCY cpu=%.0f gpu=%.0f ramp100%%" % (tc, tg)
        else:
            self.p1 += clamp(t1 - self.p1, -self.FALL * step, self.RISE * step)
            self.p2 += clamp(t2 - self.p2, -self.FALL * step, self.RISE * step)
            # кеп по шуму (см. presets.smart.caps) — снимается при перегреве
            if self.cap_on and tc < self.cap_over:
                self.p1 = clamp(self.p1, self.FLOOR, min(self.CEIL, self.cap_cpu))
            else:
                self.p1 = clamp(self.p1, self.FLOOR, self.CEIL)
            self.p2 = clamp(self.p2, self.FLOOR, min(self.CEIL, self.cap_gpu) if self.cap_on else self.CEIL)
            act = "SMART: pred %.0f/%.0f dTdt cpu=%.2f gpu=%.2f" % (t1, t2, dtc, dtg)

        w1, w2 = int(round(self.p1)), int(round(self.p2))
        changed = False
        if self.written1 is None or abs(w1 - self.written1) >= self.DEADBAND:
            changed, self.written1 = True, w1
        if self.written2 is None or abs(w2 - self.written2) >= self.DEADBAND:
            changed, self.written2 = True, w2
        if emerg:
            changed = True
            self.written1, self.written2 = w1, w2
        return w1, w2, act, changed


# --------------------------------------------------------------------------- #
# CLI helpers
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    if "--emit-env" in sys.argv:
        sys.stdout.write(emit_env())
    else:
        pr = load_preset()
        f = Fans(pr)
        print("preset=%s hp=%s writable=%s" % (pr["name"], f.hp, f.writable))
        print("mode=%s" % f.read())
