#!/usr/bin/env bash
# start.sh — (пере)запуск фоновой нагрузки. Убийство старого экземпляра делаем
# через /proc-скан, чтобы не задеть собственную командную строку (анти self-kill).
set -uo pipefail
cd "$(dirname "$0")"
SELF=$$

for pid in $(pgrep -f 'loadgen\.sh' 2>/dev/null); do
    [ "$pid" = "$SELF" ] && continue
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q 'start\.sh\|stop\.sh'; then
        continue
    fi
    kill "$pid" 2>/dev/null
done
for p in cpuburn gpuload; do pkill -x "$p" 2>/dev/null; done
sleep 1
rm -f loadgen.state loadgen.log loadgen.pid

setsid ./loadgen.sh >/dev/null 2>&1 </dev/null &
echo $! > loadgen.pid
sleep 3

echo "loadgen pid=$(cat loadgen.pid) state=$(cat loadgen.state 2>/dev/null)"

# hwmonN меняется после ребута/перезагрузки модулей — ищем по имени чипа
HP=""; CORE=""
for d in /sys/class/hwmon/hwmon*; do
    case "$(cat "$d/name" 2>/dev/null)" in
        hp) HP="$d" ;;
        coretemp) CORE="$d" ;;
    esac
done
PKG="-"
[ -n "$CORE" ] && PKG="$(($(cat "$CORE/temp1_input" 2>/dev/null || echo 0)/1000))"
RPM="-"
[ -n "$HP" ] && RPM="$(cat "$HP/fan1_input")/$(cat "$HP/fan2_input") mode=$(cat "$HP/pwm1_enable")"
echo "pkg=${PKG}C gpu=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu --format=csv,noheader,nounits 2>/dev/null) rpm=$RPM pkg_thr=$(cat /sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count 2>/dev/null)"
date +%T
