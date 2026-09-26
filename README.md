# OMEN Gaming Hub for Linux

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
```

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
├── README.md                     ← этот файл (быстрый старт)
├── START_DEVELOPMENT.md          ← ТОЧКА ВХОДА: состояние, roadmap, правила агента
├── PROGRESS_LOG.md               ← журнал контекста (статус, время, следующий шаг)
├── TZ.md                         ← полное техническое задание
├── install.sh                    ← ./install.sh [--remove] → симлинки в ~/.local/bin
├── LICENSE                       ← MIT
├── bin/                          ← все команды (сюда класть новые)
│   victus-kbd  ColorMaker  Changer  victus-report
│   victus_log.py (логирование)   i18n.py (перевод)
├── locales/                      ← ru.json, en.json (тексты интерфейса)
├── config/                       ← colors.conf, locale, profiles.d/, curves.d/
├── logs/                         ← victus.log (+ ротация .1..5)   [не в git]
├── state/                        ← report-*.txt                   [не в git]
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
