#!/usr/bin/env bash
# install.sh — symlink all victus-suite tools into ~/.local/bin.
# Everything (code, config, logs, reports) stays in this one folder.
#
#   ./install.sh           # install
#   ./install.sh --remove  # remove symlinks
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BIN="$ROOT/bin"
TARGET="${VICTUS_BIN_DIR:-$HOME/.local/bin}"

mkdir -p "$TARGET" "$ROOT/logs" "$ROOT/state" "$ROOT/config"

if [[ "${1:-}" == "--remove" ]]; then
  for f in "$BIN"/*; do
    name="$(basename "$f")"
    [[ -f "$f" ]] || continue
    [[ "$name" == *.py ]] && continue
    if [[ -L "$TARGET/$name" && "$(readlink -f "$TARGET/$name")" == "$(readlink -f "$f")" ]]; then
      rm -f "$TARGET/$name"
      echo "removed $TARGET/$name"
    fi
  done
  exit 0
fi

for f in "$BIN"/*; do
  name="$(basename "$f")"
  [[ -f "$f" ]] || continue              # skip __pycache__ and dirs
  [[ "$name" == *.py ]] && continue      # victus_log.py is a library, not a command
  ln -sfn "$f" "$TARGET/$name"
  echo "linked $TARGET/$name -> $f"
done

cat <<EOF

project : $ROOT
  bin/    executables        (linked into $TARGET)
  config/ colors.conf        (names + rgb)
  logs/   victus.log         (rotation 512 KiB x5)
  state/  report-*.txt       (victus-report output)
  docs/   research notes
  TZ.md   technical spec

try:  Changer list
      Changer pink
      victus-report
EOF
