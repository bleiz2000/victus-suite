#!/usr/bin/env bash
# finalize.sh — остановить нагрузку/страховку, вернуть BIOS AUTO и
# проконтролировать восстановление оборотов (на этой плате переход MANUAL->AUTO
# даёт ~3.5 мин с 0 RPM, поэтому мониторим и эскалируем при перегреве).
set -uo pipefail
cd "$(dirname "$0")"
HP=/sys/class/hwmon/hwmon5
CORE=$(for d in /sys/class/hwmon/hwmon*; do [ "$(cat "$d/name" 2>/dev/null)" = coretemp ] && echo $d; done)
OUT="$PWD/../../docs/logs/finalize_auto_restore.log"
: > "$OUT"

log() { echo "$(date +%T) $*" >> "$OUT"; }

# 1. нагрузка и страховка -> off
if [ -f loadgen.pid ]; then kill "$(cat loadgen.pid)" 2>/dev/null; rm -f loadgen.pid; fi
for p in cpuburn gpuload; do pkill -x "$p" 2>/dev/null; done
if [ -f guard.pid ]; then kill "$(cat guard.pid)" 2>/dev/null; fi
sleep 2
echo "idle" > loadgen.state 2>/dev/null || true

log "loadgen+guard stopped; mode=$(cat $HP/pwm1_enable) pwm=$(cat $HP/pwm1)/$(cat $HP/pwm2) rpm=$(cat $HP/fan1_input)/$(cat $HP/fan2_input)"

# 2. возврат в AUTO
echo 2 > "$HP/pwm1_enable" && log "wrote pwm1_enable=2 (AUTO)" || log "FAILED to write AUTO"

# 3. мониторинг 300 с
HOT=0
for i in $(seq 1 60); do
    sleep 5
    tc=$(( $(cat "$CORE/temp1_input") / 1000 ))
    tg=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    tg=${tg:-0}
    f1=$(cat "$HP/fan1_input"); f2=$(cat "$HP/fan2_input")
    en=$(cat "$HP/pwm1_enable")
    log "t=$((i*5))s mode=$en rpm=$f1/$f2 cpu=$tc gpu=$tg"
    # эскалация нужна и в AUTO: при нулевых оборотах перегрев нарастает
    if [ "$tc" -ge 97 ] && [ "$f1" -lt 500 ]; then HOT=$((HOT + 1)); else HOT=0; fi
    if [ "$HOT" -ge 2 ]; then
        log "ESCALATION: cpu=$tc sustained -> pwm 255"
        echo 255 > "$HP/pwm1" 2>/dev/null
        echo 255 > "$HP/pwm2" 2>/dev/null
        HOT=0
    fi
    if [ "$en" = "2" ] && [ "$f1" -ge 1000 ] && [ "$f2" -ge 1000 ] && [ "$i" -ge 6 ]; then
        log "RECOVERED at t=$((i*5))s (rpm $f1/$f2) - continuing 60s more to confirm stability"
        for j in $(seq 1 12); do
            sleep 5
            log "stable t=$((i*5 + j*5))s mode=$(cat $HP/pwm1_enable) rpm=$(cat $HP/fan1_input)/$(cat $HP/fan2_input) cpu=$(($(cat $CORE/temp1_input)/1000))"
        done
        break
    fi
done
log "finalize done: mode=$(cat $HP/pwm1_enable) rpm=$(cat $HP/fan1_input)/$(cat $HP/fan2_input)"
