#!/usr/bin/env bash
# pult.sh — запуск интерактивного пульта (сам поднимает права через sudo).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ "$(id -u)" -ne 0 ]; then
    exec sudo -p "пароль для пульта: " python3 "$HERE/fanpult.py" "$@"
fi
exec python3 "$HERE/fanpult.py" "$@"
