#!/usr/bin/env bash
# stop.sh — остановить фоновую нагрузку (вентиляторы не трогает)
set -uo pipefail
cd "$(dirname "$0")"
if [ -f loadgen.pid ]; then kill "$(cat loadgen.pid)" 2>/dev/null; rm -f loadgen.pid; fi
for p in cpuburn gpuload; do pkill -x "$p" 2>/dev/null; done
echo "idle" > loadgen.state 2>/dev/null || true
sleep 1
echo "loadgen stopped, still alive: $(pgrep -c -x loadgen.sh || echo 0)"
date +%T
