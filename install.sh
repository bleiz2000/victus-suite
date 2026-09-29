#!/usr/bin/env bash
# install.sh — victus-suite: commands into ~/.local/bin + app into the menu.
# Everything (code, config, logs, reports) stays in this one folder.
#
#   ./install.sh           # install (symlinks + "Victus Suite" menu entry + icon)
#   ./install.sh --remove  # remove symlinks, menu entry and installed icons
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BIN="$ROOT/bin"
TARGET="${VICTUS_BIN_DIR:-$HOME/.local/bin}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS="$DATA/applications"
ICONS="$DATA/icons"
DESK_ID="victus-suite"
DESKTOP="$APPS/$DESK_ID.desktop"
ICON_SRC="$ROOT/share/icons"
APP_VERSION="$(tr -d ' \n' < "$ROOT/VERSION" 2>/dev/null || echo "0")"

mkdir -p "$TARGET" "$ROOT/logs" "$ROOT/state" "$ROOT/config" "$APPS"

refresh_caches() {
  command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$APPS" >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && gtk-update-icon-cache -f -t "$ICONS/hicolor" >/dev/null 2>&1 || true
  command -v update-icon-caches >/dev/null 2>&1 \
    && update-icon-caches "$ICONS/hicolor" >/dev/null 2>&1 || true
}

install_icons() {
  if [[ ! -d "$ICON_SRC/hicolor" ]]; then
    echo "warn: no icons in $ICON_SRC/hicolor (run: python3 share/icons/make_icon.py)" >&2
    return 0
  fi
  local sz
  for sz in 16 24 32 48 64 128 256 512; do
    [[ -f "$ICON_SRC/hicolor/${sz}x${sz}/apps/$DESK_ID.png" ]] || continue
    mkdir -p "$ICONS/hicolor/${sz}x${sz}/apps"
    cp -f "$ICON_SRC/hicolor/${sz}x${sz}/apps/$DESK_ID.png" \
          "$ICONS/hicolor/${sz}x${sz}/apps/$DESK_ID.png"
  done
  if [[ -f "$ICON_SRC/hicolor/scalable/apps/$DESK_ID.svg" ]]; then
    mkdir -p "$ICONS/hicolor/scalable/apps"
    cp -f "$ICON_SRC/hicolor/scalable/apps/$DESK_ID.svg" \
          "$ICONS/hicolor/scalable/apps/$DESK_ID.svg"
  fi
  echo "icons   $ICONS/hicolor/{16..512,scalable}/apps/$DESK_ID.*"
}

install_menu() {
  cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.4
Name=Victus Suite
GenericName=Keyboard Backlight
Comment=HP Victus/OMEN keyboard backlight, effects and presets - an OMEN Gaming Hub replacement
Comment[ru]=Подсветка клавиатуры HP Victus/OMEN, эффекты и пресеты - замена OMEN Gaming Hub
TryExec=$BIN/victus_tui
Exec=$BIN/victus_tui --window
Icon=$DESK_ID
Terminal=false
StartupNotify=true
StartupWMClass=$DESK_ID
Categories=Settings;HardwareSettings;
Keywords=omen;victus;hp;backlight;rgb;keyboard;lighting;light
Keywords[ru]=омен;виктус;подсветка;клавиатура;rgb;цвет;эффекты
X-AppVersion=$APP_VERSION
X-Project-URL=https://github.com/bleiz2000/victus-suite
EOF
  chmod 644 "$DESKTOP"
  echo "menu    $DESKTOP  (Victus Suite → victus_tui --window)"
}

remove_menu() {
  if [[ -f "$DESKTOP" ]]; then
    rm -f "$DESKTOP"
    echo "removed $DESKTOP"
  fi
  local sz
  for sz in 16 24 32 48 64 128 256 512; do
    rm -f "$ICONS/hicolor/${sz}x${sz}/apps/$DESK_ID.png"
  done
  rm -f "$ICONS/hicolor/scalable/apps/$DESK_ID.svg"
  echo "removed $DESK_ID icons from $ICONS/hicolor"
}

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
  remove_menu
  refresh_caches
  exit 0
fi

for f in "$BIN"/*; do
  name="$(basename "$f")"
  [[ -f "$f" ]] || continue              # skip __pycache__ and dirs
  [[ "$name" == *.py ]] && continue      # victus_log.py is a library, not a command
  ln -sfn "$f" "$TARGET/$name"
  echo "linked $TARGET/$name -> $f"
done

install_icons
install_menu
refresh_caches

cat <<EOF

project : $ROOT   (v$APP_VERSION)
  bin/    executables        (linked into $TARGET)
  share/  icons + .desktop   (menu entry "Victus Suite")
  config/ colors.conf        (names + rgb)
  logs/   victus.log         (rotation 512 KiB x5)
  state/  report-*.txt       (victus-report output)
  docs/   research notes
  TZ.md   technical spec     ROADMAP.md  next stage

menu    : look for "Victus Suite" in your app launcher
try:  victus_tui --window
      Changer list
      Changer pink
      victus-report
EOF
