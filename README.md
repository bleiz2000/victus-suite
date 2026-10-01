# OMEN Gaming Hub for Linux

**Version:** v1.1.1 · **License:** MIT · **Repo:** `https://github.com/bleiz2000/victus-suite`

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

## Installation (v1.1.1)

**From a release (recommended):**

```bash
# dependencies (Arch/Omarchy)
sudo pacman -S --needed python python-gobject ayatana-appindicator3 foot
python -m pip install --user textual      # TUI engine (8.x)

mkdir -p ~/Work && cd ~/Work
curl -L -o vs.tar.gz https://github.com/bleiz2000/victus-suite/releases/download/v1.1.1/victus-suite.tar.gz
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

The same rule covers the fan backend: the TUI writes PWM as
`sudo -n …/bin/victus-kbd fans <cmd>` (`fans` → `vertil/tools/fanctl.py`), so
the **vertil** tab never asks for a password either.

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
| `victus-kbd fans status\|set-pwm A B\|set-mode 0\|1\|2\|hold N` | vertil fans (hwmon PWM) | via the rule above |
| `ColorMaker list\|add\|rm\|palette` | named colors (english only) | no |
| `Changer <name\|R G B\|#RRGGBB\|random\|off>` | apply color | asks sudo |
| `Changer cycle-red` | **bright red loop** (red/fire/scarlet/darkred) | asks sudo |
| `Changer cycle <colors> [--delay S]` | custom loop | asks sudo |
| `Changer stop` | stop the loop | asks sudo |
| `victus_tui [--window\|--tray]` | **TUI (v1.1-beta)** — RGB sliders + effects, **fans tab** | asks sudo |
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
victus_tui                   # TUI (v1.1.1)
```

### TUI (v1.1.1)

```bash
victus_tui                   # launch (asks sudo on EC writes)
victus_tui --window          # floating 960×540 window (foot, kitty fallback)
victus_tui --tray            # daemon + tray icon, no window
VICTUS_DRY_RUN=1 victus_tui  # launch without EC writes (safe preview)
```

The TUI is a **thin wrapper over the CLI**: every EC write goes through
`victus-kbd`, the palette comes from `victus_palette`, state is kept in
`state/last_state.json`.

- both tabs share one **dense layout**: every panel is packed top-down with
  a single blank line between blocks, and whatever space is left becomes one
  even band at the bottom of the panel (at the usual 110×31 window that band
  is 1–2 rows, so nothing is clipped and nothing floats in the middle);
- the left **COLOR PICKER** panel opens with `Cycle`/`Fade`/`Static` and the
  power switch under a divider, then the sliders, and a bottom block with
  `Hex`, the 10×5 preview and `Apply` · `Copy hex`; the right column stacks
  **Custom Effect Creator** (live sine, 1fr — the wave fills the panel) over
  **LIGHTING EFFECTS** (Effect Speed and Start / Stop);
- the tab is painted in **golden glow**: gold panel frames and titles,
  gold slider bars, gold frame around the preview, gold `Apply` / `Start`
  and a gold highlight on the active tab (the Fans tab is gold as well);
- three long ticked sliders — `Red`/`Green`/`Blue` (0…255), each with an
  exact numeric box beside it: click it and type the value — plus one
  **thin white line under them, black ↔ white** (0 = black, 50 = your colour,
  100 = white): one row, no label, no box — it is part of the panel, not a
  separate control;
- mouse input is rate-limited: drag refreshes at 60 Hz and wheel bursts
  (touchpad, smooth wheel) collapse into a few steps — the bar follows the
  pointer instead of lagging and jumping around;
- the `Hex` field previews **live while you type**; `Enter` (or `Apply`)
  sends it to the keyboard, a broken hex only restores the field;
- `Effect Speed` (0.2…5.0, also typeable) sits in the LIGHTING EFFECTS
  panel together with `Start` / `Stop`; the modes and the power switch
  live in the COLOR PICKER panel, above the sliders;
- `Apply` · `Copy hex`, status line;
- **wave speed follows Effect Speed**: amplitude and period are lerped toward
  the target every 0.12 s, no jumps;
- **calm mode**: after `Stop` the sine keeps its shape — it still fills the
  Creator panel, but the colours stand still and the phase drifts very
  slowly, so the light rests instead of going dark;
- **smart permission probe** (`probe_access`): direct write / `sudo` / EC module
  missing — the hint matches what is actually broken;
- **language button** in the title row: RU ↔ EN without restart;
- **colour cycles are smooth**: up to 64 steps per loop keeping the same
  loop period (4 s at speed 1) — the EC is written below its ~19 writes/s
  ceiling, so the fade never stutters;

The window lives in the background: `victusd` (unix socket
`$XDG_RUNTIME_DIR/victus-suite-<uid>.sock`) keeps the effect running while the
TUI is closed, `victus-tray` gives quick start/stop from the tray. Launching
the TUI starts the daemon too if it is not running yet (`ensure_daemon`).

**Fixed since alpha:** mouse-draggable ASCII sliders (no text selection).

## Fans — telemetry and control (`vertil` tab)

The TUI has two tabs: **Keyboard** (backlight) and **Fans** (`vertil`).
The fans tab answers three questions: how hot the machine is right now, who
is in charge of the blades, and what happens if something goes wrong.

### What you see

```
 CONTROL (full width)
 [*] Manual
 [ ] SMART
 [ ] BIOS Auto
 ─────────────────────────────────────────────
 Right fan [███████░░░] 128
 Left  fan [███████░░░] 128
 set 128/128
 ~1024 / 1024 RPM
 (leftover = one even band at the panel bottom)

 TELEMETRY                      SAFETY
 CPU  61.0 °C max 99            guard   CPU 99 · GPU 88 °C
 GPU  55.0 °C 42 %              smart   60..255 PWM
 VRM* board 48.2 °C             emerg   CPU 93 · GPU 83 °C
 right  2540 RPM PWM 128 50 %   hold    180 PWM
 left   2410 RPM PWM 128 50 %   preset  victus-2026-09-30
 MODE manual                    access  passwordless
 ─────────────────────────────────────────────
status: SMART ▸ 128/140
```

The knobs are the same widget as on the **Backlight** tab: a bar with a
ruler underneath, drag / wheel / arrow keys, and an exact-number box beside
it — type `128` and press Enter (or leave the box), the value is clamped to
0..255 and written 0.4 s later, like the last drag step. The tab is one
column: **CONTROL** takes the full width (modes, knobs, `set X/Y` and
`~RPM`), and below it sit **TELEMETRY** and **SAFETY** side by side, both
painted in the same gold as the Backlight tab.

Telemetry is polled once a second and is **read-only, no root**: hwmon
temperatures/RPM/PWM plus `nvidia-smi` (run in a worker thread — it can take
~3 s), so the UI never freezes while the GPU answers.

### Why it exists

- The stock firmware curve is **slow and hot**: handing the fans back to
  firmware (`set-mode 2`) stalls both blades for **~215 s** before they spin
  up again (`safety.auto_transition_zero_rpm_seconds`, measured in the
  3-phase test). On a loaded laptop that is the difference between 92 °C and
  99 °C.
- `hp-wmi` does **not** report the setpoint back: `pwm*` on read is the
  displayed RPM, jittering at ≈0.95× of what you wrote
  (`vertil/docs/2026-09-30-fan-hw-access-report.md` §7). A naive
  read-modify-write controller therefore oscillates — the tab shows the last
  command it sent instead of the trembling readback.
- Quieting a gaming laptop without cooking it needs a controller that is
  fast, visible and reversible — that is **SMART**.

### Modes

| Mode | What it does | Notes |
|---|---|---|
| **Manual** | two knobs set PWM 0..255 (0–100 %) per fan — drag them or type the exact number in the box, written 0.4 s after the last step | entering Manual is safe (the driver snapshots the current RPM) |
| **SMART** | autopilot: predictive controller, 1 s step, thresholds from `vertil/config/presets.json` | **starts on TUI launch** (first run) and is remembered, see below |
| **BIOS Auto** | hands both fans back to firmware | needs a **second click within 30 s** — see below |

The hardware mode is read honestly on every launch (one snapshot, then the
UI follows it). **Your own choice survives a restart:** first launch starts
SMART, afterwards the mode you picked (Manual / SMART / AUTO) is restored
from `state/fan_mode.json` — nothing is reset behind your back.

### Safety

1. **Leaving for BIOS Auto is confirmed twice** (30 s window): the transition
   stalls the fans for ~215 s, one accidental click should not do that.
2. **Closing the TUI in Manual mode does not leave the blades unattended**:
   the backend holds `safety.hold_pwm_on_controller_loss` (180 PWM ≈ 70 %)
   — the same rule the lab `guard.sh` uses for a dead controller.
3. **SMART stops after 10 consecutive failed writes** and says why; nothing
   is retried forever in the background.
4. **Emergency chip:** CPU ≥ 93 °C or GPU ≥ 83 °C turns the status line red.
5. **No pretend-OK:** if `hp` hwmon or the passwordless rule is missing, the
   probe verdict is printed in the SAFETY panel (`passwordless` / `sudo` /
   `need password` / `no hwmon`) instead of silently failing on the next
   write.

### How it works

```
VertilTab (Textual, 1 s poll, all blocking calls in worker threads)
 ├─ read  ─► tui/vertil_core.snapshot() ─► vertil/tools/fanlib.Sensors   no root
 │            hwmon temps/RPM/PWM + nvidia-smi
 ├─ write ─► tui/vertil_core.call("set-pwm" | "set-mode" | "hold")
 │            └─► sudo -n bin/victus-kbd fans <cmd>   ← NOPASSWD rule above
 │                └─► vertil/tools/fanctl.py ─► fanlib ─► /sys/.../hwmon*  root
 └─ controller: vertil/tools/fanlib.Smart (1 s step) lives in the TUI —
                fanctl only writes, it contains no policy
```

- **`vertil/` is self-contained**: `config/presets.json` (device, thresholds,
  provenance), `tools/fanlib.py` (sensors + controller), `tools/fanctl.py`
  (one-command-per-process write CLI), `tools/lab/` (the 3-phase test bench),
  `docs/` (hardware reports). Nothing is installed system-wide — only hwmon
  registers are written.
- **One fan = one physical side:** right = CPU = `pwm1`/`fan1`,
  left = GPU = `pwm2`/`fan2`.
- The SMART loop **keeps running while you use the keyboard tab**; the
  telemetry poll pauses only when the fans tab is hidden and no autopilot is
  active.
- The same backend is usable without the TUI:
  `victus-kbd fans status | set-pwm A B | set-mode 0|1|2 | hold N`.

**Status:** console pult + TUI tab are integrated, verified with a headless
smoke suite and validated live on this machine: SMART starts from the tab,
the chosen mode is restored on relaunch, closing the window holds 180 PWM
(logs + `vertil/docs/2026-09-30-tui-integration-session.md` §7).

## Interface language (localization)

Default is **English (us)**. Messages live in `locales/<code>.json`,
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
├── VERSION                       ← 1.1.1 (single source of truth)
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
│     screens.py (Bento layout, tabs, language button)
│     kbd_tab.py (color/effect panels, kill_loop, calm)
│     vertil_tab.py (fans tab: telemetry, modes, SMART loop)
│     vertil_core.py (read/write bridge, sudo -n probe, hold on exit)
│     slider.py (ASCII sliders, SineWave)
├── vertil/                       ← fan backend, self-contained
│   ├── config/                   ← presets.json: device, thresholds, provenance
│   ├── tools/                    ← fanlib.py (sensors + SMART), fanctl.py (write CLI)
│   │   └── lab/                  ← 3-phase test bench (cpuburn, gpuload, guard)
│   └── docs/                     ← hardware reports + measured test logs
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
