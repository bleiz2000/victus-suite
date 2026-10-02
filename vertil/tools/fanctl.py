#!/usr/bin/env python3
"""fanctl — команды записи вентиляторов для TUI-вкладки «vertil».

Одна команда — один процесс; TUI без root зовёт её как подкоманду
NOPASSWD-бинарника подсветки: `sudo -n bin/victus-kbd fans <cmd>` — пароль
не спрашивается (см. README про sudoers). Никакой логики управления здесь нет:
контроллер живёт в TUI (как в fanpult), fanctl только пишет в hwmon.

    status           JSON-снимок hp-hwmon (режим, PWM, RPM)
    set-pwm P1 P2    записать PWM (fanlib сам заходит в MANUAL)
    set-mode M       0=MAX, 1=MANUAL, 2=AUTO
    hold PWM         аварийный уровень обеих лопастей (presets.safety.hold_pwm)

Коды возврата: 0 — ок, 1 — ошибка записи/аргументов/прав, 2 — железо недоступно.
Все настройки берутся из vertil/config/presets.json.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fanlib as F  # noqa: E402


def usage(msg: str) -> int:
    print("fanctl: %s" % msg, file=sys.stderr)
    print("usage: fanctl.py status | set-pwm <0..255> [<0..255>] | "
          "set-mode <0|1|2> | hold <0..255>", file=sys.stderr)
    return 1


def number(raw: str, what: str, err: list) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        err.append("%s должен быть числом: %r" % (what, raw))
        return -1
    if not 0 <= value <= F.PWM_MAX:
        err.append("%s вне 0..%d: %d" % (what, F.PWM_MAX, value))
        return -1
    return value


def main(argv) -> int:
    if not argv:
        return usage("нет команды")
    cmd = argv[0]

    try:
        preset = F.load_preset()
    except (OSError, ValueError) as e:
        print("fanctl: presets.json: %s" % e, file=sys.stderr)
        return 2

    fans = F.Fans(preset)
    if not fans.available:
        print("fanctl: hp hwmon не найден (chip=%s)"
              % preset["sensors"]["fan_chip"], file=sys.stderr)
        return 2

    # 1. разбор аргументов — неверная команда важнее отсутствия прав
    if cmd == "status":
        print(json.dumps(fans.read(), ensure_ascii=False))
        return 0

    if cmd == "set-pwm":
        if len(argv) not in (2, 3):
            return usage("set-pwm ждит одно или два числа")
        bad: list = []
        p1 = number(argv[1], "pwm1", bad)
        # один канал (драйвер без pwm2) — второй аргумент необязателен
        p2 = number(argv[2], "pwm2", bad) if len(argv) == 3 else p1
        if bad:
            print("fanctl: " + "; ".join(bad), file=sys.stderr)
            return 1
        plan = ("set-pwm", p1, p2)

    elif cmd == "set-mode":
        if len(argv) != 2:
            return usage("set-mode ждёт 0|1|2")
        bad = []
        mode = number(argv[1], "mode", bad)
        if bad:
            print("fanctl: " + "; ".join(bad), file=sys.stderr)
            return 1
        if mode not in tuple(fans.modes):
            print("fanctl: неизвестный режим %d (доступно: %s)"
                  % (mode, ", ".join(str(m) for m in sorted(fans.modes))),
                  file=sys.stderr)
            return 1
        plan = ("set-mode", mode, None)

    elif cmd == "hold":
        if len(argv) != 2:
            return usage("hold ждёт один уровень PWM")
        bad = []
        level = number(argv[1], "hold", bad)
        if bad:
            print("fanctl: " + "; ".join(bad), file=sys.stderr)
            return 1
        plan = ("set-pwm", level, level)

    else:
        return usage("неизвестная команда '%s'" % cmd)

    # 2. права: запись в pwm* только от root
    if not fans.writable:
        wanted = [fans.enable_attr, fans.cpu_pwm_out, fans.gpu_pwm_out]
        missing = [a for a in wanted
                   if a and not os.path.exists(os.path.join(fans.hp or "", a))]
        if missing:
            # отсутствие файла — не отсутствие прав: врать про root нельзя
            print("нет атрибутов: %s — драйвер не экспортирует их"
                  % ", ".join(missing), file=sys.stderr)
            return 2
        print("нет прав: нужен root (sudo)", file=sys.stderr)
        return 1

    # 3. запись
    kind, first, second = plan[0], plan[1], plan[2]
    if kind == "set-pwm":
        # set_pwm сам заходит в MANUAL: запись в pwm* при enable!=1 даёт -EINVAL
        err = fans.set_pwm(first, second)
    else:
        # enter_manual не даёт лишней записи: драйвер снапшотит RPM без скачка
        err = fans.enter_manual() if first == 1 else fans.set_mode(first)

    if err:
        print("fanctl: %s" % err, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
