#!/usr/bin/env python3
"""Сравнительный анализ логов трёх фаз теста вентиляторов HP Victus."""
import csv, math, os

LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../docs/logs")

FILES = [
    ("P1a", "БИОС AUTO (без инжектир. нагрузки)", "phase1a_bios_auto_noinjected_load.csv"),
    ("P1",  "БИОС AUTO (+ нагрузка CPU/GPU)",     "phase1_bios_auto.csv"),
    ("P2",  "ФАЗА 2 «ТОПОР» 100%",                "phase2_brutal.csv"),
    ("P3",  "ФАЗА 3 SMART (предиктивный)",        "phase3_smart.csv"),
]


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = (len(s) - 1) * q
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (i - lo)


def mean(v):
    return sum(v) / len(v) if v else None


def sd(v):
    if len(v) < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def steps(v, thr):
    return sum(1 for a, b in zip(v, v[1:]) if abs(b - a) >= thr)


def col(rows, k):
    return [num(r.get(k)) for r in rows if num(r.get(k)) is not None]


def analyse(key, title, fn):
    p = os.path.join(LOGS, fn)
    if not os.path.exists(p):
        return None
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    t = [num(r.get("t")) for r in rows if num(r.get("t")) is not None]
    dur = (max(t) - min(t)) if len(t) >= 2 else len(rows)
    if dur <= 0:
        dur = len(rows)
    mins = dur / 60.0

    cpu, cpumax = col(rows, "t_cpu"), col(rows, "t_cpu_max")
    gpu, vrm = col(rows, "t_gpu"), col(rows, "t_vrm")
    f1, f2 = col(rows, "fan1"), col(rows, "fan2")
    p1, p2 = col(rows, "pwm1"), col(rows, "pwm2")
    busy = col(rows, "cpu_busy")
    thr = col(rows, "pkg_thr")
    thrms = col(rows, "pkg_thr_ms")
    freq = col(rows, "freq_avg")
    kind = [r.get("load_kind", "-") for r in rows]

    thr_d = (max(thr) - min(thr)) if len(thr) >= 2 else 0
    thrms_d = (max(thrms) - min(thrms)) if len(thrms) >= 2 else 0
    busym = mean(busy) or 0

    return dict(
        key=key, title=title, n=len(rows), dur=dur, mins=mins,
        cpu=cpu, cpumax=cpumax, gpu=gpu, vrm=vrm, f1=f1, f2=f2,
        p1=p1, p2=p2, busy=busy, freq=freq, kind=kind,
        busym=busym,
        full_cpu=(sum(1 for x in p1 if x >= 250) / len(p1) * 100) if p1 else 0,
        full_gpu=(sum(1 for x in p2 if x >= 250) / len(p2) * 100) if p2 else 0,
        hi_cpu=(sum(1 for x in f1 if x >= 5500) / len(f1) * 100) if f1 else 0,
        hi_gpu=(sum(1 for x in f2 if x >= 5500) / len(f2) * 100) if f2 else 0,
        st1=steps(f1, 200), st2=steps(f2, 200),
        sp1=steps(p1, 40), sp2=steps(p2, 40),
        thr_d=thr_d, thr_min=thr_d / mins if mins else 0,
        thrms_d=thrms_d, thrms_min=thrms_d / mins if mins else 0,
        per_busy=(thr_d / mins / busym * 100) if busym else None,
    )


DATA = [a for a in (analyse(*f) for f in FILES) if a]
W = 11
HDR = 36
LINE = "-" * (HDR + (W + 3) * len(DATA))


def line(label, getter, fmt="{:>11.1f}"):
    out = label.ljust(HDR)
    for d in DATA:
        v = getter(d)
        out += " | " + (fmt.format(v) if isinstance(v, (int, float)) else " " * W)
    return out


print("СРАВНЕНИЕ ФАЗ".ljust(HDR) + "".join(" | " + d["key"].rjust(W) for d in DATA))
print(LINE)
print("Описание:".ljust(HDR) + "".join(" | " for d in DATA))
for d in DATA:
    print(f"  {d['key']:<4} {d['title']}")
print(LINE)
print(line("Длительность, с", lambda d: d["dur"], "{:>11.0f}"))
print(line("Выборок", lambda d: d["n"], "{:>11.0f}"))
print(line("Средний busy, %", lambda d: d["busym"]))
print(line("Время PWM CPU >=250, %", lambda d: d["full_cpu"]))
print(line("Время PWM GPU >=250, %", lambda d: d["full_gpu"]))
print(line("Время Fan1 >=5500, %", lambda d: d["hi_cpu"]))
print(line("Время Fan2 >=5500, %", lambda d: d["hi_gpu"]))
print(LINE)
print(line("Tcpu сред, C", lambda d: mean(d["cpu"])))
print(line("Tcpu p95, C", lambda d: pct(d["cpu"], .95)))
print(line("Tcpu max, C", lambda d: max(d["cpu"]) if d["cpu"] else None))
print(line("Tcore max, C", lambda d: max(d["cpumax"]) if d["cpumax"] else None))
print(line("Tgpu сред, C", lambda d: mean(d["gpu"])))
print(line("Tgpu p95, C", lambda d: pct(d["gpu"], .95)))
print(line("Tgpu max, C", lambda d: max(d["gpu"]) if d["gpu"] else None))
print(line("Tvrm сред, C", lambda d: mean(d["vrm"])))
print(line("Tvrm max, C", lambda d: max(d["vrm"]) if d["vrm"] else None))
print(LINE)
print(line("Fan1 сред, RPM", lambda d: mean(d["f1"])))
print(line("Fan2 сред, RPM", lambda d: mean(d["f2"])))
print(line("Fan1 sd, RPM", lambda d: sd(d["f1"])))
print(line("Fan2 sd, RPM", lambda d: sd(d["f2"])))
print(line("Резких скачков Fan1 (>=200)", lambda d: d["st1"], "{:>11.0f}"))
print(line("Резких скачков Fan2 (>=200)", lambda d: d["st2"], "{:>11.0f}"))
print(line("Смен уровня PWM CPU (>=40)", lambda d: d["sp1"], "{:>11.0f}"))
print(line("Смен уровня PWM GPU (>=40)", lambda d: d["sp2"], "{:>11.0f}"))
print(LINE)
print(line("pkg_throttle всего", lambda d: d["thr_d"], "{:>11.0f}"))
print(line("pkg_throttle /мин", lambda d: d["thr_min"], "{:>11.0f}"))
print(line("throttle_ms всего", lambda d: d["thrms_d"], "{:>11.0f}"))
print(line("throttle_ms /мин", lambda d: d["thrms_min"], "{:>11.0f}"))
print(line("throttle/мин на 1% busy", lambda d: d["per_busy"], "{:>11.0f}"))
print(line("Freq avg, MHz", lambda d: mean(d["freq"]), "{:>11.0f}"))
print(LINE)

print("\nДоля времени по режимам нагрузки (load_kind):")
for d in DATA:
    tot = len(d["kind"]) or 1
    ks = sorted({k for k in d["kind"] if k and k != "-"})
    print("  %-4s %s" % (d["key"], ", ".join(f"{k}={d['kind'].count(k)*100//tot}%" for k in ks)))

print("\nFan1 p05/p50/p95, RPM:")
for d in DATA:
    print("  %-4s %6.0f / %6.0f / %6.0f" % (
        d["key"], pct(d["f1"], .05) or 0, pct(d["f1"], .5) or 0, pct(d["f1"], .95) or 0))

print("\nFan2 p05/p50/p95, RPM:")
for d in DATA:
    print("  %-4s %6.0f / %6.0f / %6.0f" % (
        d["key"], pct(d["f2"], .05) or 0, pct(d["f2"], .5) or 0, pct(d["f2"], .95) or 0))

print("\nPWM CPU p05/p50/p95 (доля времени на максимуме = шум):")
for d in DATA:
    print("  %-4s %6.0f / %6.0f / %6.0f" % (
        d["key"], pct(d["p1"], .05) or 0, pct(d["p1"], .5) or 0, pct(d["p1"], .95) or 0))
