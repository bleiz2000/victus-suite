# OMEN Gaming Hub for Linux

**Version:** v1.1-alpha · **License:** MIT · **Repo:** `https://github.com/bleiz2000/victus-suite`

An OMEN Gaming Hub analogue for Linux: HP Victus/OMEN keyboard backlight,
power modes, fans, monitoring and overlay (Shift+F2 replacement).
Local project folder: `~/Work/victus-suite` → GitHub `victus-suite`.

> **Vibe Coding** — the project is built with active support of an AI agent
> together with the user. Development starts at **`START_DEVELOPMENT.md`**
> (current state, roadmap, agent rules).

**Strategy — simple first:** stage 1 (basic CLI: light, fans, temperatures),
stage 2 (TUI on Textual), stage 3 (effects and power profiles).
Details — `START_DEVELOPMENT.md` §4.

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
| `victus_tui` | **TUI (alpha)** — backlight tab: presets, HSV, effects | asks sudo |
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
victus_tui                   # TUI (alpha, v1.1)
```

### TUI (v1.1-alpha)

```bash
victus_tui                   # launch (asks sudo on EC writes)
VICTUS_DRY_RUN=1 victus_tui  # launch without EC writes (safe preview)
```

The TUI is a **thin wrapper over the CLI**: every EC write goes through
`victus-kbd`, the palette comes from `victus_palette`, state is kept in
`state/last_state.json`.

- power switch, 48 built-in presets + your own colors;
- HSV sliders with live preview: `rgb() / #hex / hsv()`;
- `Apply` · `Copy hex` · `Save as name`;
- `Cycle` effect with speed, `Start` / `Stop`, status line.

**Known alpha issues (planned for v1.2):** sliders select text instead of
dragging with the mouse, and the design looks rough. Next stage:
**Material Design & Animation Overhaul** (Material Design 3, rounded frames,
working mouse/drag sliders, smooth indicators).

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
├── TZ.md                         ← full technical specification
├── install.sh                    ← ./install.sh [--remove] → symlinks to ~/.local/bin
├── LICENSE                       ← MIT
├── bin/                          ← all commands (put new ones here)
│   victus-kbd  ColorMaker  Changer  victus-report  victus_tui
│   victus_log.py (logging)   i18n.py (translations)   victus_palette.py
│   tui/                          ← TUI modules: screens, kbd_tab, slider
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

**Версия:** v1.1-alpha · **Лицензия:** MIT · **Репозиторий:** `https://github.com/bleiz2000/victus-suite`

Аналог OMEN Gaming Hub для Linux: подсветка клавиатуры HP Victus/OMEN,
режимы питания, вентиляторы, мониторинг и оверлей (замена Shift+F2).
Локальная папка проекта: `~/Work/victus-suite` → GitHub `victus-suite`.

> **Vibe Coding** — проект создаётся при активной поддержке AI-агента
> в связке с пользователем. Начало разработки: **`START_DEVELOPMENT.md`**
> (текущее состояние, дорожная карта, правила агента).

**Стратегия — сначала простое:** этап 1 (базовый CLI: свет, фены, температуры),
этап 2 (TUI на Textual), этап 3 (эффекты и профили питания).
Подробности — `START_DEVELOPMENT.md` §4.

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
| `victus_tui` | **TUI (альфа)** — вкладка «Подсветка»: пресеты, HSV, эффекты | спросит sudo |
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
victus_tui                   # TUI (альфа, v1.1)
```

### TUI (v1.1-alpha)

```bash
victus_tui                   # запуск (при записи в EC спросит sudo)
VICTUS_DRY_RUN=1 victus_tui  # запуск без записи в EC (безопасный предпросмотр)
```

TUI — **тонкая обёртка над CLI**: каждая запись в EC идёт через `victus-kbd`,
палитра берётся из `victus_palette`, состояние хранится в
`state/last_state.json`.

- переключатель питания, 48 встроенных пресетов + свои цвета;
- слайдеры HSV с живым предпросмотром: `rgb() / #hex / hsv()`;
- `Применить` · `Копировать hex` · `Сохранить как имя`;
- эффект `Cycle` со скоростью, `Старт` / `Стоп`, строка статуса.

**Известные косяки альфы (запланировано на v1.2):** слайдеры выделяют текст
вместо перетаскивания мышью, дизайн выглядит топорно. Следующий этап:
**Material Design & Animation Overhaul** (Material Design 3, скруглённые
рамки, работающие слайдеры с мышью/драгом, плавные индикаторы).

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
├── TZ.md                         ← полное техническое задание
├── install.sh                    ← ./install.sh [--remove] → симлинки в ~/.local/bin
├── LICENSE                       ← MIT
├── bin/                          ← все команды (сюда класть новые)
│   victus-kbd  ColorMaker  Changer  victus-report  victus_tui
│   victus_log.py (логирование)   i18n.py (перевод)   victus_palette.py
│   tui/                          ← модули TUI: screens, kbd_tab, slider
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
