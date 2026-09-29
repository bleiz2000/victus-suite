# OMEN Gaming Hub for Linux

**Version:** v1.0.0-beta · **License:** MIT · **Repo:** `https://github.com/bleiz2000/victus-suite`

> **English (primary)** · [Русская версия →](README.ru.md)

An OMEN Gaming Hub analogue for Linux: HP Victus/OMEN keyboard backlight,
power modes, fans, monitoring and overlay (Shift+F2 replacement).
Local project folder: `~/Work/victus-suite` → GitHub `victus-suite`.

> **Vibe Coding** — the project is built with active support of an AI agent
> together with the user. Development starts at **`START_DEVELOPMENT.md`**
> (current state, roadmap, agent rules).

**Strategy — simple first:** stage 1 (basic CLI: light, fans, temperatures),
stage 2 (TUI on Textual), stage 3 (effects and power profiles).
Details — `START_DEVELOPMENT.md` §4.

## Installation (v1.0.0-beta)

**From a release (recommended):**

```bash
# dependencies (Arch/Omarchy)
sudo pacman -S --needed python python-gobject ayatana-appindicator3 foot
python -m pip install --user textual      # TUI engine (8.x)

mkdir -p ~/Work && cd ~/Work
curl -L -o vs.tar.gz https://github.com/bleiz2000/victus-suite/releases/download/v1.0.0-beta/victus-suite.tar.gz
tar xzf vs.tar.gz && cd victus-suite
./install.sh                              # symlinks + menu entry
```

**From source:**

```bash
git clone https://github.com/bleiz2000/victus-suite.git ~/Work/victus-suite
cd ~/Work/victus-suite && ./install.sh
```

`./install.sh` also creates the **`Victus Suite`** entry in your application
menu (`~/.local/share/applications/victus-suite.desktop`, `Exec=… --window`,
black-and-white icon in `~/.local/share/icons/hicolor/`) — launch it from the
launcher, no terminal needed.

**Optional — passwordless EC writes** (otherwise every write asks for sudo):

```bash
echo "$USER ALL=(root) NOPASSWD: $PWD/bin/victus-kbd" | sudo tee /etc/sudoers.d/victus-suite
sudo chmod 440 /etc/sudoers.d/victus-suite
```

**Run:**

```bash
victus_tui --window    # floating 960×540 window (foot)
victus_tui             # in the current terminal
victus_tui --tray      # background daemon + tray icon only
victus-tray            # tray icon: open window / start-stop effect / quit
```

…or simply press **Victus Suite** in your application menu.

Remove with `./install.sh --remove` (symlinks, menu entry and icons).

## What works right now

| Command | What it does | Root |
|---|---|---|
| `victus-kbd <preset\|RGB>` | backlight color (EC write) | yes |
| `victus-kbd cycle <c...> [--delay S] [--bg]` | color loop in background | yes |
| `victus-kbd stop` | stop the loop | yes |
| `victus-kbd get` / `dump [start] [len]` | current RGB / EC dump | yes |
| `ColorMaker list\|add\|rm\|palette` | named colors (english only) | no |
| `Changer <name\|R G B\|#RRGGBB\|random\|off>` | apply color | asks sudo |
| `Changer cycle-red` | **bright red loop** (red/fire/scarlet/darkred) | asks sudo |
| `Changer cycle <colors> [--delay S]` | custom loop | asks sudo |
| `Changer stop` | stop the loop | asks sudo |
| `victus_tui [--window\|--tray]` | **TUI (v1.0-beta)** — Bento 960×540: presets, HSV, effects | asks sudo |
| `victusd [--verbose\|--quit]` | background daemon (unix socket, keeps effects alive) | no |
| `victus-tray` | tray icon: open window / start-stop effect / quit | no |
| `victus-report [--with-ec]` | diagnostics + logs into one file | no |

Code: `bin/` (symlinks into `~/.local/bin` are created by `./install.sh`)
Config: `config/colors.conf`, language: `config/locale`
Locales: `locales/ru.json`, `locales/en.json`
Log: `logs/victus.log` (rotation 512 KiB × 5)
Reports: `state/report-<date>.txt`

### Examples

```bash
Changer red                  # pure red 255,0,0 (most visible)
Changer cycle-red            # bright red loop in background
Changer stop                 # stop
Changer cycle red fire darkred --delay 1   # custom loop
Changer pink                 # pink 255,105,180
Changer "#ff00ff"            # arbitrary hex
Changer 120 200 255          # arbitrary RGB
Changer random
ColorMaker add mycolor 30 144 255   # your own name (english)
Changer mycolor
victus_tui                   # TUI (beta, v1.0.0-beta)
```

### TUI (v1.0.0-beta)

```bash
victus_tui                   # launch (asks sudo on EC writes)
victus_tui --window          # floating 960×540 window (foot, kitty fallback)
victus_tui --tray            # daemon + tray icon, no window
VICTUS_DRY_RUN=1 victus_tui  # launch without EC writes (safe preview)
```

The TUI is a **thin wrapper over the CLI**: every EC write goes through
`victus-kbd`, the palette comes from `victus_palette`, state is kept in
`state/last_state.json`.

- compact **Bento 960×540** layout: PRESETS / COLOR PICKER / LIGHTING EFFECTS;
- power switch, 48 built-in presets + your own colors;
- HSV sliders with live preview: `rgb() / #hex / hsv()`;
- `Apply` · `Copy hex` · `Save as name`;
- `Cycle`/`Fade`/`Solid` effects, `Start` / `Stop`, status line;
- **wave speed follows Effect Speed**: amplitude and period are lerped toward
  the target every 0.12 s, no jumps;
- **calm mode**: after `Stop` the sine flattens into a straight coloured line
  with a barely visible live wobble — the light never dims;
- **smart permission probe** (`probe_access`): direct write / `sudo` / EC module
  missing — the hint matches what is actually broken;
- **language button** in the title row: RU ↔ EN without restart.

The window lives in the background: `victusd` (unix socket
`$XDG_RUNTIME_DIR/victus-suite-<uid>.sock`) keeps the effect running while the
TUI is closed, `victus-tray` gives quick start/stop from the tray.

**Fixed since alpha:** mouse-draggable ASCII sliders (no text selection).
Remaining for v1.1+ — see `ROADMAP.md`.

## Interface language (localization)

Default is **Russian**. Messages live in `locales/<code>.json`,
the current language is in `config/locale`.

```bash
VICTUS_LANG=en Changer list        # language on the fly
echo en > config/locale            # default language
cp locales/ru.json locales/de.json # add a new language
```

How to add a language: copy `ru.json`, translate the values (keep the keys),
set the code in `config/locale` or in `VICTUS_LANG`. Fallback — `en.json`.

## Logs and diagnostics

```bash
tail -f ~/Work/victus-suite/logs/victus.log   # what happened
VICTUS_LOG=debug Changer pink                # verbose log of one command
victus-report                                # report for a bug (no root)
victus-report --with-ec                      # + EC dump (asks sudo)
```

Every log line looks like this:

```
2026-09-25T20:27:56+04:00 ERROR pid=37009 euid=1000 Changer: unknown color 'nosuchcolor'
2026-09-25T20:27:56+04:00 INFO  pid=37011 euid=1000 victus-kbd: rgb (255,255,255) -> (255,105,180)
```

`euid` immediately shows whether a command failed because root was missing.
Exceptions are logged with a full traceback, stderr gets a short reason +
the path to the log.

## Project structure (everything in one folder)

```
victus-suite/
├── README.md                     ← this file (English, primary)
├── README.ru.md                  ← русская версия / Russian version
├── START_DEVELOPMENT.md          ← ENTRY POINT: state, roadmap, agent rules
├── PROGRESS_LOG.md               ← context journal (status, time, next step)
├── ROADMAP.md                    ← next stage: script → installable app
├── TZ.md                         ← full technical specification
├── VERSION                       ← 1.0.0-beta (single source of truth)
├── install.sh                    ← ./install.sh [--remove] → symlinks + menu entry + icons
├── share/
│   └── icons/                    ← black&white icon: victus-suite.svg, hicolor PNGs, make_icon.py
├── LICENSE                       ← MIT
├── bin/                          ← all commands (put new ones here)
│   victus-kbd  Changer  ColorMaker  victus-report
│   victus_tui  victusd  victus-tray
│   victus_log.py (logging)   i18n.py (translations)   victus_palette.py
│   tui/                          ← TUI modules
│     core.py (EC/sudo probe, engine, delay_for_speed)
│     screens.py (Bento layout, language button)
│     kbd_tab.py (presets/picker/effects, kill_loop, calm)
│     slider.py (ASCII sliders, SineWave)
├── locales/                      ← ru.json, en.json (interface texts)
├── config/                       ← colors.conf, locale, profiles.d/, curves.d/
├── logs/                         ← victus.log (+ rotation .1..5)   [not in git]
├── state/                        ← report-*.txt, last_state.json   [not in git]
└── docs/
    ├── 01-chto-sdelano.md        ← how the backlight is done, what is verified
    ├── 02-audit-sistemy.md       ← system audit for this machine
    ├── 03-podsvetka-rgb.md       ← RGB: EC, WMI, risks, product plan
    ├── 04-ventilyatory.md        ← fans: hwmon/pwm, timings, risks
    ├── 05-rezhimy.md             ← Comfort/Balanced/Performance, FAQ
    └── 06-overlay-i-upravlenie.md← overlay (Shift+F2 replacement), CPU/GPU power
```

Reinstall after moving/cloning: `./install.sh`.

## Machine

- HP Victus 16-r0xxx, i5-13500H, RTX 4060 Laptop
- Kernel `7.2.5-3-omarchy`, driver `hp-wmi` (upstream, with hwmon-fan support)
- OS: Omarchy (Arch-based), Hyprland
