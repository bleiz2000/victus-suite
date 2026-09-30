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
echo "pkg=$(($(cat /sys/class/hwmon/hwmon7/temp1_input)/1000))C gpu=$(nvidia-smi --query-gpu=temperature.gpu,utilization.gpu --format=csv,noheader,nounits) rpm=$(cat /sys/class/hwmon/hwmon5/fan1_input)/$(cat /sys/class/hwmon/hwmon5/fan2_input) mode=$(cat /sys/class/hwmon/hwmon5/pwm1_enable) pkg_thr=$(cat /sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count)"
date +%T
