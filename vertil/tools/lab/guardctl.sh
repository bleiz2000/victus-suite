#!/usr/bin/env bash
# guardctl.sh — (пере)запуск страховочного демона от root, без самозавершения.
set -uo pipefail
cd "$(dirname "$0")"
SELF=$$

for pid in $(pgrep -f 'guard\.sh' 2>/dev/null); do
    [ "$pid" = "$SELF" ] && continue
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q 'guardctl' && continue
    kill "$pid" 2>/dev/null
done
sleep 1

GUARD_LOG="$PWD/guard.log" setsid ./guard.sh >/dev/null 2>&1 </dev/null &
echo $! > guard.pid
sleep 2
echo "guard pid=$(cat guard.pid) alive=$(pgrep -f 'tools/lab/guard\.sh' | wc -l) hp=$(for d in /sys/class/hwmon/hwmon*; do [ "$(cat $d/name 2>/dev/null)" = hp ] && echo $d; done)"
