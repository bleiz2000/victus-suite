#!/usr/bin/env python3
"""Трёхфазный лабораторный прогон: логирование температур/оборотов + управление вентиляторами.

  phase 1 : read-only, вентиляторы остаются в BIOS AUTO (ничего не пишем)
  phase 2 : «топор» — bang-bang 100% / базовый уровень
  phase 3 : интеллектуальный предиктивный контроллер

Сырые логи: vertil/docs/logs/phase<N>.csv
"""
import argparse
import csv
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import fanlib as F  # noqa: E402

LAB = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.normpath(os.path.join(LAB, "..", "..", "docs", "logs"))
STATE = os.path.join(LAB, "loadgen.state")

CSV_COLS = [
    "ts", "elapsed", "phase", "load_kind",
    "t_cpu", "t_cpu_max", "t_gpu", "t_vrm", "t_board", "t_dimm",
    "fan1", "fan2", "pwm1", "pwm2", "mode",
    "cpu_busy", "pkg_thr", "pkg_thr_ms", "core_thr", "core_thr_ms",
    "gpu_util", "gpu_clk", "freq_avg",
    "tgt1", "tgt2", "action",
]


def _read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def _find_hwmon(want):
    hits = []
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        if _read(os.path.join(d, "name")) == want:
            hits.append(d)
    return hits


def _find_tz(want):
    for d in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        if _read(os.path.join(d, "type")) == want:
            return d
    return None


def _mv(path, scale=1000.0):
    v = _read(path)
    try:
        return round(float(v) / scale, 1)
    except (TypeError, ValueError):
        return None


class Sensors:
    def __init__(self):
        self.hp = _find_hwmon("hp")[0]
        cores = _find_hwmon("coretemp")
        self.core = cores[0] if cores else None
        self.spd = _find_hwmon("spd5118")
        self.tz_vrm = _find_tz("TCPU_PCI") or _find_tz("acpitz")
        self.tz_board = _find_tz("acpitz")
        self._prev_stat = self._stat()
        self._prev_ts = time.monotonic()

    @staticmethod
    def _stat():
        try:
            with open("/proc/stat") as fh:
                parts = fh.readline().split()
            vals = [float(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0.0)
            total = sum(vals)
            return idle, total
        except Exception:
            return 0.0, 1.0

    def cpu_busy(self):
        idle, total = self._stat()
        p_idle, p_total = self._prev_stat
        self._prev_stat = (idle, total)
        d_total = total - p_total
        if d_total <= 0:
            return 0.0
        return round(100.0 * (1.0 - (idle - p_idle) / d_total), 1)

    @staticmethod
    def _gpu():
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,clocks.sm",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3).stdout.strip().split(",")
            return float(out[0]), float(out[1]), float(out[2])
        except Exception:
            return None, None, None

    def read(self):
        t_cpu = _mv(os.path.join(self.core, "temp1_input")) if self.core else None
        t_max = None
        if self.core:
            vals = []
            for f in glob.glob(os.path.join(self.core, "temp*_input")):
                v = _mv(f)
                if v is not None:
                    vals.append(v)
            t_max = max(vals) if vals else None
        g_t, g_u, g_c = self._gpu()
        dims = [v for v in (_mv(os.path.join(d, "temp1_input")) for d in self.spd) if v]
        return {
            "t_cpu": t_cpu,
            "t_cpu_max": t_max,
            "t_gpu": g_t,
            "t_vrm": _mv(os.path.join(self.tz_vrm, "temp")) if self.tz_vrm else None,
            "t_board": _mv(os.path.join(self.tz_board, "temp")) if self.tz_board else None,
            "t_dimm": max(dims) if dims else None,
            "fan1": _read(os.path.join(self.hp, "fan1_input")),
            "fan2": _read(os.path.join(self.hp, "fan2_input")),
            "pwm1": _read(os.path.join(self.hp, "pwm1")),
            "pwm2": _read(os.path.join(self.hp, "pwm2")) or _read(os.path.join(self.hp, "pwm1")),
            "mode": _read(os.path.join(self.hp, "pwm1_enable")),
            "gpu_util": g_u,
            "gpu_clk": g_c,
            "pkg_thr": _read("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count"),
            "pkg_thr_ms": _read("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_total_time_ms"),
            "core_thr": _read("/sys/devices/system/cpu/cpu0/thermal_throttle/core_throttle_count"),
            "core_thr_ms": _read("/sys/devices/system/cpu/cpu0/thermal_throttle/core_throttle_total_time_ms"),
            "cpu_busy": self.cpu_busy(),
            "freq_avg": self._freq_avg(),
            "load_kind": (_read(STATE) or "-").strip(),
        }

    @staticmethod
    def _freq_avg():
        vals = []
        for i in range(16):
            v = _read("/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq" % i)
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        return round(sum(vals) / len(vals) / 1000.0, 0) if vals else None


# ---------------------------------------------------------------- контроллеры
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def write_pwm(fans, p1, p2):
    """Запись через fanlib: он знает про одноканальный PWM (нет pwm2)."""
    err = fans.set_pwm(p1, p2)
    if err:
        print("write_pwm failed: %s" % err, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, required=True, choices=[1, 2, 3])
    ap.add_argument("--minutes", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--exit-pwm", type=int, default=160)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sensors = Sensors()
    hp = sensors.hp

    preset = F.load_preset()
    fans = F.Fans(preset)
    if not fans.available:
        print("hp hwmon не найден", file=sys.stderr)
        return 2
    ctrl = None
    if a.phase == 2:
        ctrl = F.Brutal(preset)
    elif a.phase == 3:
        ctrl = F.Smart(preset)

    if a.phase > 1:
        # переход AUTO -> MANUAL: драйвер снапшотит текущий RPM, скачка нет
        if not fans.writable:
            print("нет прав на запись — запускайте от root", file=sys.stderr)
            return 2
        err = fans.enter_manual() or fans.set_mode(1)
        if err:
            print("cannot enter MANUAL: %s" % err, file=sys.stderr)
            return 2
        time.sleep(1.0)

    print("phase=%d duration=%.1f min out=%s mode=%s shared_pwm=%s"
          % (a.phase, a.minutes, a.out, _read(os.path.join(hp, "pwm1_enable")),
             fans.shared_pwm), flush=True)

    end = time.monotonic() + a.minutes * 60.0
    t0 = time.monotonic()
    prev = t0
    next_tick = t0
    next_print = t0 + 5.0
    n = 0

    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()

        while True:
            now = time.monotonic()
            if now >= end:
                break
            s = sensors.read()
            dt = max(0.0, now - prev)
            prev = now

            tgt1 = tgt2 = action = ""
            changed = False
            if ctrl is not None:
                tgt1, tgt2, action, changed = ctrl.update(s, dt)
                if changed and not write_pwm(fans, tgt1, tgt2):
                    action += " [WRITE FAILED]"

            row = {
                "ts": round(time.time(), 3),
                "elapsed": round(now - t0, 1),
                "phase": a.phase,
                "load_kind": s["load_kind"],
                "t_cpu": s["t_cpu"], "t_cpu_max": s["t_cpu_max"], "t_gpu": s["t_gpu"],
                "t_vrm": s["t_vrm"], "t_board": s["t_board"], "t_dimm": s["t_dimm"],
                "fan1": s["fan1"], "fan2": s["fan2"],
                "pwm1": s["pwm1"], "pwm2": s["pwm2"], "mode": s["mode"],
                "cpu_busy": s["cpu_busy"], "pkg_thr": s["pkg_thr"],
                "pkg_thr_ms": s["pkg_thr_ms"], "core_thr": s["core_thr"],
                "core_thr_ms": s["core_thr_ms"],
                "gpu_util": s["gpu_util"], "gpu_clk": s["gpu_clk"],
                "freq_avg": s["freq_avg"],
                "tgt1": tgt1, "tgt2": tgt2, "action": action,
            }
            w.writerow(row)
            n += 1

            if now >= next_print:
                next_print = now + 5.0
                print("t=%5.0fs cpu=%s/%s gpu=%s vrm=%s board=%s rpm=%s/%s pwm=%s/%s "
                      "mode=%s busy=%s%% load=%s thr=%s freq=%s"
                      % (now - t0, s["t_cpu"], s["t_cpu_max"], s["t_gpu"], s["t_vrm"],
                         s["t_board"], s["fan1"], s["fan2"], s["pwm1"], s["pwm2"],
                         s["mode"], s["cpu_busy"], s["load_kind"], s["pkg_thr"],
                         s["freq_avg"]),
                      flush=True)

            sleep = next_tick + 1.0 - time.monotonic()
            next_tick += 1.0
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_tick = time.monotonic()

    fh.close()
    if ctrl is not None:
        write_pwm(fans, a.exit_pwm, a.exit_pwm)
        print("exit handoff pwm=%d (mode=%s)" % (a.exit_pwm, _read(os.path.join(hp, "pwm1_enable"))),
              flush=True)
    print("phase %d done: %d rows -> %s" % (a.phase, n, a.out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
