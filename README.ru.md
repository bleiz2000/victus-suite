# OMEN Gaming Hub для Linux

> [English (primary) →](README.md) · **Русская версия**

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
curl -L -o vs.tar.gz https://github.com/bleiz2000/victus-suite/releases/download/v1.0.0-beta/victus-suite.tar.gz
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
├── README.md                     ← основной файл (English, primary)
├── README.ru.md                  ← этот файл (русская версия)
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
