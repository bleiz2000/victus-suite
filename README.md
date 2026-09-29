# OMEN Gaming Hub for Linux

**Version:** v1.0.0-beta · **License:** MIT · **Repo:** `https://github.com/bleiz2000/victus-suite`

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
curl -L -o vs.tar.gz https://github.com/bleiz2000/victus-suite/releases/latest/download/victus-suite.tar.gz
tar xzf vs.tar.gz && cd victus-suite
./install.sh                              # symlinks into ~/.local/bin
```

**From source:**

```bash
git clone https://github.com/bleiz2000/victus-suite.git ~/Work/victus-suite
cd ~/Work/victus-suite && ./install.sh
```

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

Remove with `./install.sh --remove`.

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
├── README.md                     ← this file (quick start), EN + RU
├── START_DEVELOPMENT.md          ← ENTRY POINT: state, roadmap, agent rules
├── PROGRESS_LOG.md               ← context journal (status, time, next step)
├── ROADMAP.md                    ← next stage: script → installable app
├── TZ.md                         ← full technical specification
├── VERSION                       ← 1.0.0-beta (single source of truth)
├── install.sh                    ← ./install.sh [--remove] → symlinks to ~/.local/bin
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

---

# OMEN Gaming Hub для Linux

**Версия:** v1.0.0-beta · **Лицензия:** MIT · **Репозиторий:** `https://github.com/bleiz2000/victus-suite`

Аналог OMEN Gaming Hub для Linux: подсветка клавиатуры HP Victus/OMEN,
режимы питания, вентиляторы, мониторинг и оверлей (замена Shift+F2).
Локальная папка проекта: `~/Work/victus-suite` → GitHub `victus-suite`.

> **Vibe Coding** — проект создаётся при активной поддержке AI-агента
> в связке с пользователем. Начало разработки: **`START_DEVELOPMENT.md`**
> (текущее состояние, дорожная карта, правила агента).

**Стратегия — сначала простое:** этап 1 (базовый CLI: свет, фены, температуры),
этап 2 (TUI на Textual), этап 3 (эффекты и профили питания).
Подробности — `START_DEVELOPMENT.md` §4.

## Установка (v1.0.0-beta)

**Из релиза (рекомендуется):**

```bash
# зависимости (Arch/Omarchy)
sudo pacman -S --needed python python-gobject ayatana-appindicator3 foot
python -m pip install --user textual      # движок TUI (8.x)

mkdir -p ~/Work && cd ~/Work
curl -L -o vs.tar.gz https://github.com/bleiz2000/victus-suite/releases/latest/download/victus-suite.tar.gz
tar xzf vs.tar.gz && cd victus-suite
./install.sh                              # симлинки в ~/.local/bin
```

**Из исходников:**

```bash
git clone https://github.com/bleiz2000/victus-suite.git ~/Work/victus-suite
cd ~/Work/victus-suite && ./install.sh
```

**Опционально — запись в EC без пароля** (иначе каждый запрос — ввод sudo):

```bash
echo "$USER ALL=(root) NOPASSWD: $PWD/bin/victus-kbd" | sudo tee /etc/sudoers.d/victus-suite
sudo chmod 440 /etc/sudoers.d/victus-suite
```

**Запуск:**

```bash
victus_tui --window    # всплывающее окно 960×540 (foot)
victus_tui             # в текущем терминале
victus_tui --tray      # только фоновый демон + иконка в трее
victus-tray            # трей: открыть окно / старт-стоп эффекта / выход
```

Удаление: `./install.sh --remove`.

## Что уже работает сейчас

| Команда | Что делает | Root |
|---|---|---|
| `victus-kbd <preset\|RGB>` | Цвет подсветки (запись в EC) | да |
| `victus-kbd cycle <c...> [--delay S] [--bg]` | Цикл цветов в фоне | да |
| `victus-kbd stop` | Остановить цикл | да |
| `victus-kbd get` / `dump [start] [len]` | Текущий RGB / дамп EC | да |
| `ColorMaker list\|add\|rm\|palette` | Именованные цвета (только english) | нет |
| `Changer <имя\|R G B\|#RRGGBB\|random\|off>` | Применить цвет | спросит sudo |
| `Changer cycle-red` | **Цикл ярко-красных** (red/fire/scarlet/darkred) | спросит sudo |
| `Changer cycle <цвета> [--delay S]` | Свой цикл | спросит sudo |
| `Changer stop` | Остановить цикл | спросит sudo |
| `victus_tui [--window\|--tray]` | **TUI (v1.0-beta)** — Bento 960×540: пресеты, HSV, эффекты | спросит sudo |
| `victusd [--verbose\|--quit]` | фоновый демон (unix-сокет, держит эффекты живыми) | нет |
| `victus-tray` | иконка в трее: открыть окно / старт-стоп / выход | нет |
| `victus-report [--with-ec]` | Диагностика + логи в один файл | нет |

Код: `bin/` (симлинки в `~/.local/bin` ставит `./install.sh`)
Конфиг: `config/colors.conf`, язык: `config/locale`
Локали: `locales/ru.json`, `locales/en.json`
Лог: `logs/victus.log` (ротация 512 KiB × 5)
Отчёты: `state/report-<дата>.txt`

### Примеры

```bash
Changer red                  # чистый красный 255,0,0 (самый заметный)
Changer cycle-red            # цикл ярко-красных в фоне
Changer stop                 # остановить
Changer cycle red fire darkred --delay 1   # свой цикл
Changer pink                 # розовый 255,105,180
Changer "#ff00ff"            # произвольный hex
Changer 120 200 255          # произвольный RGB
Changer random
ColorMaker add mycolor 30 144 255   # своё имя (english)
Changer mycolor
victus_tui                   # TUI (бета, v1.0.0-beta)
```

### TUI (v1.0.0-beta)

```bash
victus_tui                   # запуск (при записи в EC спросит sudo)
victus_tui --window          # всплывающее окно 960×540 (foot, запасной kitty)
victus_tui --tray            # только демон + иконка в трее
VICTUS_DRY_RUN=1 victus_tui  # запуск без записи в EC (безопасный предпросмотр)
```

TUI — **тонкая обёртка над CLI**: каждая запись в EC идёт через `victus-kbd`,
палитра берётся из `victus_palette`, состояние хранится в
`state/last_state.json`.

- компактный макет **Bento 960×540**: ПРЕСЕТЫ / ВЫБОР ЦВЕТА / ЭФФЕКТЫ;
- переключатель питания, 48 встроенных пресетов + свои цвета;
- слайдеры HSV с живым предпросмотром: `rgb() / #hex / hsv()`;
- `Применить` · `Копировать hex` · `Сохранить как имя`;
- эффекты `Цикл`/`Затухание`/`Статичный`, `Старт` / `Стоп`, строка статуса;
- **скорость волны идёт от «Скорости эффекта»**: амплитуда и период
  доезжают к цели лерпом за 0.12 с, без рывков;
- **спокойный режим**: после `Стоп` синус выравнивается в ровную цветную
  линию с еле заметным живым колыханием — свет не гаснет;
- **умная проверка прав** (`probe_access`): прямая запись / `sudo` / модуль
  EC не загружен — подсказка про то, что реально сломано;
- **кнопка языка** в заголовке: RU ↔ EN без перезапуска.

Окно живёт в фоне: `victusd` (unix-сокет `$XDG_RUNTIME_DIR/victus-suite-<uid>.sock`)
держит эффект работающим, когда TUI закрыт, а `victus-tray` даёт быстрый
старт-стоп из трея.

**Исправлено с альфы:** слайдеры тянутся мышью (текст больше не выделяется).
Остальное на следующий этап — см. `ROADMAP.md`.

## Язык интерфейса (локализация)

По умолчанию **русский**. Сообщения лежат в `locales/<код>.json`,
текущий язык — в файле `config/locale`.

```bash
VICTUS_LANG=en Changer list        # язык на лету
echo en > config/locale            # язык по умолчанию
cp locales/ru.json locales/de.json # добавить новый язык
```

Как добавить язык: скопировать `ru.json`, перевести значения (ключи не трогать),
указать код в `config/locale` или в `VICTUS_LANG`. Fallback — `en.json`.

## Логи и диагностика

```bash
tail -f ~/Work/victus-suite/logs/victus.log   # что происходило
VICTUS_LOG=debug Changer pink                # подробный лог одной команды
victus-report                                # отчёт для бага (без root)
victus-report --with-ec                      # + дамп EC (спросит sudo)
```

Каждая запись в лог выглядит так:

```
2026-09-25T20:27:56+04:00 ERROR pid=37009 euid=1000 Changer: unknown color 'nosuchcolor'
2026-09-25T20:27:56+04:00 INFO  pid=37011 euid=1000 victus-kbd: rgb (255,255,255) -> (255,105,180)
```

`euid` сразу показывает, упало ли из-за отсутствия root. Исключения пишутся
с полным traceback в лог, в stderr — короткая причина + путь к логу.

## Структура проекта (всё в одной папке)

```
victus-suite/
├── README.md                     ← этот файл (быстрый старт), EN + RU
├── START_DEVELOPMENT.md          ← ТОЧКА ВХОДА: состояние, roadmap, правила агента
├── PROGRESS_LOG.md               ← журнал контекста (статус, время, следующий шаг)
├── ROADMAP.md                    ← следующий этап: скрипт → устанавливаемое приложение
├── TZ.md                         ← полное техническое задание
├── VERSION                       ← 1.0.0-beta (источник правды по версии)
├── install.sh                    ← ./install.sh [--remove] → симлинки в ~/.local/bin
├── LICENSE                       ← MIT
├── bin/                          ← все команды (сюда класть новые)
│   victus-kbd  Changer  ColorMaker  victus-report
│   victus_tui  victusd  victus-tray
│   victus_log.py (логирование)   i18n.py (перевод)   victus_palette.py
│   tui/                          ← модули TUI
│     core.py (EC/проверка прав, движок, delay_for_speed)
│     screens.py (макет Bento, кнопка языка)
│     kbd_tab.py (пресеты/пикер/эффекты, kill_loop, calm)
│     slider.py (ASCII-слайдеры, SineWave)
├── locales/                      ← ru.json, en.json (тексты интерфейса)
├── config/                       ← colors.conf, locale, profiles.d/, curves.d/
├── logs/                         ← victus.log (+ ротация .1..5)   [не в git]
├── state/                        ← report-*.txt, last_state.json   [не в git]
└── docs/
    ├── 01-chto-sdelano.md        ← как сделана подсветка, что проверено
    ├── 02-audit-sistemy.md       ← что выставлено на конкретной машине
    ├── 03-podsvetka-rgb.md       ← RGB: EC, WMI, риски, план продукта
    ├── 04-ventilyatory.md        ← вентиляторы: hwmon/pwm, тайминги, риски
    ├── 05-rezhimy.md             ← Comfort/Balanced/Performance, FAQ «это одно и то же?»
    └── 06-overlay-i-upravlenie.md← оверлей (замена Shift+F2), CPU/GPU power
```

Переустановка после переноса/клонирования: `./install.sh`.

## Машинa

- HP Victus 16-r0xxx, i5-13500H, RTX 4060 Laptop
- Ядро `7.2.5-3-omarchy`, драйвер `hp-wmi` (upstream, с поддержкой hwmon-fan)
- ОС: Omarchy (Arch-based), Hyprland
