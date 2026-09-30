#!/usr/bin/env python3
"""fanpult — интерактивный терминальный пульт вентиляторов HP Victus.

Живой вывод: температуры CPU/GPU/VRM, энергопотребление, обороты, режим, статус.
Любая цифра на вводе мгновенно устанавливает этот уровень PWM (0..255).

Запуск:
    sudo python3 vertil/tools/fanpult.py            # полный доступ (запись)
    python3 vertil/tools/fanpult.py                 # только наблюдение
    sudo python3 vertil/tools/fanpult.py --plain    # одна строка на тик (логи)
    echo 180 | sudo python3 vertil/tools/fanpult.py --plain   # скриптованный режим

Команды:  0-255 = оба вентилятора    c0-255 = только CPU    g0-255 = только GPU
          a = вернуть AUTO (BIOS)    m = 100 % (MAX)        s = автопилот SMART
          ? = справка                q = выход

Ничего не пишет в систему: все настройки берутся из vertil/config/presets.json.
"""
from __future__ import annotations

import argparse
import os
import select
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fanlib as F  # noqa: E402

RED, GRN, YEL, CYN, DIM, BLD, RST = ("\033[31m", "\033[32m", "\033[33m",
                                     "\033[36m", "\033[2m", "\033[1m", "\033[0m")
CLEAR = "\033[H\033[2J"


def c(val, color):
    if val is None:
        return "-"
    return "%s%s%s" % (color, val, RST)


def temp_color(t, warn=85, hot=95):
    if t is None:
        return DIM
    return GRN if t < warn else YEL if t < hot else RED


def bar(v, width=20, mx=255):
    if v is None:
        return ""
    n = int(round(max(0, min(mx, v)) / mx * width))
    return CYN + "█" * n + DIM + "░" * (width - n) + RST


def fmt_w(v):
    return "-" if v is None else "%.1f W" % v


def fmt_rpm(v):
    return "-" if v is None else "%d RPM" % v


class Pult:
    def __init__(self, args):
        self.args = args
        self.preset = F.load_preset()
        self.sensors = F.Sensors(self.preset)
        self.fans = self.sensors.fans
        cur = self.fans.read()
        self.smart = F.Smart(self.preset, seed=(cur.get("pwm1") or 79, cur.get("pwm2") or 92))
        self.busy_prev = None
        self.autopilot = False
        self.input = ""
        self.status = "готово — введите цифру 0..255"
        self.status_err = False
        self.help_on = True
        self.last = None
        self.pending = ""
        self.setpoint = [None, None]      # что мы ЗАДАЛИ (PWM), пока EC не догонит
        self._auto_armed = 0.0
        self.thr_prev = None
        self.thr_time = time.monotonic()
        self.thr_rate = None
        self.running = True
        self.started = time.monotonic()
        self.plain = args.plain or not sys.stdout.isatty()

    AUTO_WARN = ("переход MANUAL->AUTO на этой плате глушит вентиляторы на ~215 с "
                 "(даже если режим уже AUTO). Повторите 'a' в течение 30 с")

    # ---------------- команды ---------------- #
    def parse(self, raw):
        cmd = raw.strip().lower()
        if not cmd:
            return None
        if cmd in ("q", "quit", "exit"):
            return ("quit", None)
        if cmd in ("a", "auto"):
            return ("mode", 2)
        if cmd in ("m", "max"):
            return ("mode", 0)
        if cmd in ("s", "smart"):
            return ("smart", None)
        if cmd in ("?", "h", "help"):
            return ("help", None)
        if cmd[:1] in "cg" and cmd[1:].isdigit():
            return (cmd[0], int(cmd[1:]))
        if cmd.isdigit():
            v = int(cmd)
            if 0 <= v <= 255:
                return ("both", v)
        return ("bad", cmd)

    def warn_cold_start(self, pwm):
        t = self.last.get("t_cpu") if self.last else None
        rpm = pwm / self.preset["fans"]["pwm_max"] * self.preset["device"]["max_cpu_rpm"]
        if t is not None and t >= 92 and rpm < 2500:
            return ("внимание: CPU %s °C при %d RPM — опасно низко" %
                    ("%.0f" % t, rpm), True)
        return None

    def exec(self, raw):
        p = self.parse(raw)
        if p is None:
            return
        kind, val = p
        if kind == "quit":
            self.running = False
            return
        if kind == "help":
            self.help_on = not self.help_on
            return
        if kind == "bad":
            self.say("неизвестная команда: %s (нажмите ?)" % val, err=True)
            return
        if kind == "smart":
            self.autopilot = not self.autopilot
            self.say("автопилот SMART %s" % ("ВКЛ" if self.autopilot else "выкл"))
            return
        if not self.fans.writable:
            self.say("нет прав на запись — запустите через sudo", err=True)
            return

        if kind == "mode":
            if val == 2:
                now = time.monotonic()
                if abs(now - self._auto_armed) > 30.0:
                    self._auto_armed = now
                    self.say(self.AUTO_WARN, err=True)
                    return
                self._auto_armed = 0.0
            err = self.fans.set_mode(val)
            name = self.fans.modes.get(val, val)
            if err:
                self.say("ошибка режима %s: %s" % (name, err), err=True)
            else:
                self.autopilot = False
                self.setpoint = [None, None]
                self.say("режим -> %s" % name.upper())
            return

        if kind in ("both", "cpu", "gpu"):
            if val is None or not 0 <= val <= 255:
                self.say("PWM должен быть 0..255", err=True)
                return
            cur = self.fans.read()
            p1 = val if kind in ("both", "cpu") else (cur.get("pwm1") or val)
            p2 = val if kind in ("both", "gpu") else (cur.get("pwm2") or val)
            err = self.fans.set_pwm(p1, p2)
            if err:
                self.say("ошибка записи: %s" % err, err=True)
                return
            self.autopilot = False
            self.setpoint = [p1, p2]
            self.say("мгновенно: %s" % self._target_label(p1, p2))
            w = self.warn_cold_start(min(p1, p2))
            if w:
                self.say(w[0], err=True)
            return

    @staticmethod
    def _target_label(p1, p2):
        mx = 255
        r1 = int(round(p1 / mx * 5800))
        r2 = int(round(p2 / mx * 5800))
        return "PWM %d/%d  ~%d/%d RPM" % (p1, p2, r1, r2)

    def say(self, msg, err=False):
        self.status, self.status_err = msg, err
        if self.plain and getattr(self, "_printed_status", None) != (msg, err):
            self._printed_status = (msg, err)
            sys.stdout.write("# %s%s\n" % ("ошибка: " if err else "", msg))
            sys.stdout.flush()

    # ---------------- опрос ---------------- #
    def tick(self):
        d = self.sensors.read(self.busy_prev)
        self.busy_prev = d.get("busy_prev")
        self.last = d
        now = time.monotonic()

        if d.get("thr") is not None:
            if self.thr_prev is not None:
                dt = now - self.thr_time
                if dt > 0.5:
                    self.thr_rate = (d["thr"] - self.thr_prev) / dt * 60.0
            self.thr_prev, self.thr_time = d["thr"], now

        if self.autopilot and self.fans.writable:
            p1, p2, act, changed = self.smart.update(d, self.args.interval)
            if changed:
                err = self.fans.set_pwm(p1, p2)
                if err:
                    self.say("автопилот: %s" % err, err=True)
                else:
                    self.setpoint = [p1, p2]
                    self.say(act)

    # ---------------- отрисовка ---------------- #
    def frame(self):
        d = self.last
        if not d:
            return "опрос..."
        pr, f = self.preset, self.fans
        cpu, gmax = d.get("t_cpu"), d.get("t_cpu_max")
        gpu, vrm, brd = d.get("t_gpu"), d.get("t_vrm"), d.get("t_board")
        pw = (d.get("cpu_w") or 0) + (d.get("gpu_w") or 0)
        mode = d.get("mode_name") or "-"
        ctrl = ("АВТОПИЛОТ SMART" if self.autopilot else
                ("РУЧНОЙ" if mode == "manual" else mode.upper()))
        root = "root" if os.geteuid() == 0 else "read-only"
        gap = 66

        L = []
        up = time.monotonic() - self.started
        L.append("%s VICTUS FAN PULT %s  preset %s  %s  %s  uptime %.0f s"
                 % (BLD, RST, c(pr["name"], CYN), c(root, GRN if root == "root" else YEL),
                    time.strftime("%H:%M:%S"), up))
        L.append(DIM + "─" * gap + RST)

        L.append(" CPU  %s   max %s   пакет %s   %s MHz   busy %s%%"
                 % (c("%.1f °C" % cpu if cpu is not None else None, temp_color(cpu)),
                    c("%.1f °C" % gmax if gmax is not None else None, temp_color(gmax)),
                    c(fmt_w(d.get("cpu_w")), CYN),
                    c(d.get("freq"), DIM), c("%.0f" % d["cpu_busy"] if d.get("cpu_busy") is not None else None, DIM)))
        L.append(" GPU  %s   util %s%%   %s   %s/%s MHz"
                 % (c("%.1f °C" % gpu if gpu is not None else None, temp_color(gpu)),
                    c("%.0f" % d["gpu_util"] if d.get("gpu_util") is not None else None, DIM),
                    c(fmt_w(d.get("gpu_w")), CYN),
                    c(d.get("sm"), DIM), c(d.get("mem"), DIM)))
        L.append(" VRM* %s   board %s   энергия %s   thr %s%s"
                 % (c("%.1f °C" % vrm if vrm is not None else None, temp_color(vrm)),
                    c("%.1f °C" % brd if brd is not None else None, DIM),
                    c(fmt_w(pw) if (d.get("cpu_w") or d.get("gpu_w")) else None, GRN),
                    c(d.get("thr"), DIM),
                    c("  (+%d/мин)" % self.thr_rate, YEL) if self.thr_rate is not None else ""))
        L.append(DIM + "─" * gap + RST)

        mx = pr["fans"]["pwm_max"]
        sp1, sp2 = self.setpoint
        L.append(" FAN1 CPU  %s   duty %s%%   задано %s   %s" %
                 (c(fmt_rpm(d.get("fan1")), GRN if (d.get("pwm1") or 0) < 250 else YEL),
                  str(int(round((d.get("pwm1") or 0) / mx * 100))).rjust(3),
                  c(sp1, CYN) if sp1 is not None else DIM + "-" + RST,
                  bar(sp1 if sp1 is not None else d.get("pwm1"))))
        L.append(" FAN2 GPU  %s   duty %s%%   задано %s   %s" %
                 (c(fmt_rpm(d.get("fan2")), GRN if (d.get("pwm2") or 0) < 250 else YEL),
                  str(int(round((d.get("pwm2") or 0) / mx * 100))).rjust(3),
                  c(sp2, CYN) if sp2 is not None else DIM + "-" + RST,
                  bar(sp2 if sp2 is not None else d.get("pwm2"))))
        if sp1 is not None:
            L.append(" %sвентиляторы инерционны: RPM догоняет заданное ~10 с%s" % (DIM, RST))
        L.append(" MODE  %s     %s" %
                 (c(mode.upper(), {"auto": GRN, "manual": YEL, "max": RED}.get(mode, DIM)),
                  c(ctrl, CYN if self.autopilot else DIM)))
        L.append(DIM + "─" * gap + RST)

        sc = RED if self.status_err else GRN
        L.append(" %s> %s%s   %s%s" % (BLD, self.input, RST, c(self.status, sc), RST))
        if self.help_on:
            L.append(" %s0-255=оба  c<0-255>=cpu  g<0-255>=gpu  a=AUTO  m=100%%  s=SMART  ?=помощь  q=выход%s"
                     % (DIM, RST))
        L.append(" %s* VRM — ACPI-прокси TCPU_PCI (собственного датчика VRM нет)%s" % (DIM, RST))
        return "\n".join(L)

    def plain_frame(self):
        d = self.last
        if not d:
            return None
        return ("%s cpu=%s gpu=%s vrm=%s w=%s/%s rpm=%s/%s pwm=%s/%s mode=%s busy=%s thr=%s"
                % (time.strftime("%H:%M:%S"),
                   d.get("t_cpu"), d.get("t_gpu"), d.get("t_vrm"),
                   d.get("cpu_w"), d.get("gpu_w"),
                   d.get("fan1"), d.get("fan2"), d.get("pwm1"), d.get("pwm2"),
                   d.get("mode_name"), d.get("cpu_busy"), d.get("thr")))

    def render(self):
        if self.plain:
            line = self.plain_frame()
            if line:
                sys.stdout.write(line + "\n")
        else:
            sys.stdout.write(CLEAR + self.frame() + "\n")
        sys.stdout.flush()

    # ---------------- ввод ---------------- #
    def feed(self, data: str, tty: bool):
        if tty:
            for ch in data:
                if ch in ("\x03", "\x04"):          # Ctrl-C / Ctrl-D
                    self.running = False
                elif ch in ("\r", "\n"):
                    cmd, self.input = self.input, ""
                    self.exec(cmd)
                elif ch in ("\x7f", "\x08"):
                    self.input = self.input[:-1]
                elif ch == "\x1b":
                    self.input = ""
                elif ch.isprintable():
                    self.input += ch
        else:
            self.pending += data
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                if line.strip():
                    self.exec(line)

    # ---------------- главный цикл ---------------- #
    def run(self):
        fd = sys.stdin.fileno()
        tty = sys.stdin.isatty()
        old = None
        if tty:
            import termios
            import tty as _tty
            old = termios.tcgetattr(fd)
            _tty.setcbreak(fd)
        interval = max(0.2, float(self.args.interval))
        duration = float(self.args.duration or 0)
        deadline = (time.monotonic() + duration) if duration > 0 else None
        eof = False
        watch_fd = True

        self.tick()
        self.render()
        nxt = time.monotonic() + interval
        try:
            while self.running:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    break
                timeout = max(0.0, min(nxt, deadline or nxt) - now) if deadline else max(0.0, nxt - now)
                r = []
                if watch_fd:
                    try:
                        r, _, _ = select.select([fd], [], [], timeout)
                    except (ValueError, OSError):
                        break
                else:
                    select.select([], [], [], timeout)
                if r:
                    try:
                        data = os.read(fd, 4096).decode(errors="ignore")
                    except OSError:
                        data = ""
                    if data:
                        self.feed(data, tty)
                        if tty:
                            self.render()
                    else:
                        # EOF: перестаём опрашивать stdin, иначе busy-loop на закрытом пайпе
                        eof = True
                        watch_fd = False
                        if deadline is None:
                            deadline = time.monotonic() + float(self.args.grace)
                if time.monotonic() >= nxt:
                    self.tick()
                    self.render()
                    nxt = time.monotonic() + interval
        finally:
            if old is not None:
                import termios
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write("\n")
            sys.stdout.flush()
        self.finish()

    def finish(self):
        d = self.fans.read()
        print("выход: режим=%s pwm=%s/%s rpm=%s/%s autopilot=%s"
              % (d.get("mode_name"), d.get("pwm1"), d.get("pwm2"),
                 d.get("fan1"), d.get("fan2"), self.autopilot))
        if d.get("mode") == 1:
            print("вентиляторы остаются в РУЧНОМ режиме. Вернуть AUTO:")
            print("  echo 2 | sudo tee %s/%s" % (self.fans.hp, self.fans.enable_attr))
            print("  (запись 2 глушит вентиляторы ~215 с — делайте на простое или перезагрузкой)")


def main():
    ap = argparse.ArgumentParser(description="интерактивный пульт вентиляторов HP Victus")
    ap.add_argument("-i", "--interval", type=float, default=1.0, help="период опроса, с")
    ap.add_argument("-d", "--duration", type=float, default=0,
                    help="остановиться через N секунд (0 = без ограничения)")
    ap.add_argument("--grace", type=float, default=5.0,
                    help="сколько дожидаться после EOF stdin, с")
    ap.add_argument("--plain", action="store_true", help="одна строка на тик (без ANSI)")
    a = ap.parse_args()
    p = Pult(a)
    if not p.fans.available:
        print("hp hwmon не найден — датчики недоступны", file=sys.stderr)
        return 1
    print("пресет %s загружен из %s" % (p.preset["name"], F.CONFIG))
    if not p.fans.writable:
        p.say("только наблюдение: нужен root для управления", err=True)
    p.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
