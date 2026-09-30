#!/usr/bin/env bash
# loadgen.sh — АДАПТИВНАЯ фоновая нагрузка на CPU и GPU.
#
# Принципы (анти-лаг):
#   * nice 19 + ionice -c3  -> уступает любым интерактивным приложениям
#   * affinity 2-15         -> P-core0 (cpu0/cpu1) свободен для десктопа/IRQ
#   * гистерезис по temp/busy -> при горячем железе наша нагрузка ПАУЗИРУЕТСЯ,
#     при занятости юзера снижается степень
#   * чередование           -> 40 с CPU-удар, 40 с GPU-удар (с duty-cycle)
set -uo pipefail
LAB=$(cd "$(dirname "$0")" && pwd)
[ -f "$LAB/../../config/presets.env" ] && . "$LAB/../../config/presets.env"
STATE="$LAB/loadgen.state"

pkg_temp() {
    local d v
    for d in /sys/class/hwmon/hwmon*; do
        [ "$(cat "$d/name" 2>/dev/null)" = "coretemp" ] || continue
        v=$(cat "$d/temp1_input" 2>/dev/null) || continue
        [ -n "$v" ] || continue
        echo $(( v / 1000 ))
        return 0
    done
    echo 0
}

cpu_busy() {
    read -r _ a b c d e f g <<<"$(grep '^cpu ' /proc/stat)"
    local idle=$((d + e)) total=0 x
    for x in $a $b $c $d $e $f $g; do total=$((total + x)); done
    echo "$idle $total"
}

gpu_util() {
    nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc '0-9'
}

prev=$(cpu_busy)
prev_t=$(date +%s)

echo "idle" > "$STATE"
trap 'echo "idle" > "$STATE"; exit 0' INT TERM EXIT

while true; do
    cur=$(cpu_busy); now=$(date +%s)
    read -r pi pt <<<"$prev"; read -r ci ct <<<"$cur"
    dt=$((ct - pt)); db=0
    [ "$dt" -gt 0 ] && db=$((100 * (100 * (dt - (ci - pi)) / dt) / 100))
    prev="$cur"
    T=$(pkg_temp); U=$(gpu_util); U=${U:-0}

    if [ "${T:-0}" -ge "${LOADGEN_YIELD_CPU:-96}" ] || [ "$db" -ge 85 ] || [ "${U:-0}" -ge 92 ]; then
        MODE="yield"; STATE_KIND="yield"; CPU_T=0; GPU_D=0
    elif [ "${T:-0}" -ge "${LOADGEN_LIGHT_CPU:-90}" ] || [ "$db" -ge 70 ] || [ "${U:-0}" -ge 80 ]; then
        MODE="light"; STATE_KIND="cpu"; CPU_T=3; GPU_D=40
    else
        MODE="full"; STATE_KIND="cpu"; CPU_T=8; GPU_D=85
    fi

    echo "loadgen: busy=${db}% pkg=${T}C gpu=${U}% -> $MODE" >> "$LAB/loadgen.log"

    if [ "$MODE" = "yield" ]; then
        echo "yield" > "$STATE"
        sleep 15
        continue
    fi

    echo "$STATE_KIND" > "$STATE"
    if [ "$CPU_T" -gt 0 ]; then
        taskset -c 2-15 nice -n 19 ionice -c3 "$LAB/cpuburn" "$CPU_T" 40 >/dev/null 2>&1 &
        wait $! 2>/dev/null
    else
        sleep 40
    fi

    echo "idle" > "$STATE"
    sleep 5

    echo "gpu" > "$STATE"
    nice -n 19 ionice -c3 "$LAB/gpuload" 40 "$GPU_D" >/dev/null 2>&1 &
    G=$!
    taskset -c 2-15 nice -n 19 ionice -c3 "$LAB/cpuburn" 2 40 >/dev/null 2>&1 &
    C=$!
    wait $G 2>/dev/null
    wait $C 2>/dev/null

    echo "idle" > "$STATE"
    sleep 5
done
