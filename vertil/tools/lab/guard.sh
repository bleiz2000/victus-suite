#!/usr/bin/env bash
# guard.sh — независимая страховка на время фаз 2/3 (нужен root).
#   1) контроллер (phase.py) умер/повис  -> увести вентиляторы в безопасный режим 180
#   2) насыщенный перегрев (CPU>=99C держится >=9 с ИЛИ GPU>=88C) -> 100%
#      Порог сознательно высокий: кремний сам защищается на Tjmax,
#      guard страхует от ПО, а не подменяет контроллер в штатном режиме.
set -uo pipefail
LAB="$(cd "$(dirname "$0")" && pwd)"
[ -f "$LAB/../../config/presets.env" ] && . "$LAB/../../config/presets.env"
HP=""
for d in /sys/class/hwmon/hwmon*; do
    [ -r "$d/name" ] || continue
    [ "$(cat "$d/name" 2>/dev/null)" = "hp" ] && [ -e "$d/pwm1" ] && { HP="$d"; break; }
done
[ -n "$HP" ] || { echo "guard: hp hwmon not found" >&2; exit 1; }

CORE=""
for d in /sys/class/hwmon/hwmon*; do
    [ -r "$d/name" ] || continue
    [ "$(cat "$d/name" 2>/dev/null)" = "coretemp" ] && { CORE="$d"; break; }
done

LOG="${GUARD_LOG:-/dev/null}"
HOT=0
trap 'exit 0' INT TERM

while true; do
    mode=$(cat "$HP/pwm1_enable" 2>/dev/null || echo 2)
    if [ "$mode" = "1" ]; then
        tc=0; tg=0
        [ -n "$CORE" ] && tc=$(( $(cat "$CORE/temp1_input" 2>/dev/null || echo 0) / 1000 ))
        tg=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
        tg=${tg:-0}

        if [ "$tc" -ge "${GUARD_CPU_HOT:-99}" ]; then HOT=$((HOT + 1)); else HOT=0; fi

        if [ "$HOT" -ge "${GUARD_CPU_STREAK:-3}" ] || [ "$tg" -ge "${GUARD_GPU_HOT:-88}" ]; then
            echo "GUARD: emergency 100% (cpu=$tc gpu=$tg streak=$HOT)" >> "$LOG"
            echo 255 > "$HP/pwm1" 2>/dev/null
            echo 255 > "$HP/pwm2" 2>/dev/null
        elif ! pgrep -f "phase.py" >/dev/null 2>&1; then
            echo "GUARD: controller gone -> hold 180 (cpu=$tc gpu=$tg)" >> "$LOG"
            echo "${GUARD_HOLD_PWM:-180}" > "$HP/pwm1" 2>/dev/null
            echo "${GUARD_HOLD_PWM:-180}" > "$HP/pwm2" 2>/dev/null
            exit 0
        fi
    fi
    sleep "${GUARD_POLL_S:-3}"
done
