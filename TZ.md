# ТЕХНИЧЕСКОЕ ЗАДАНИЕ

**Проект:** **OMEN Gaming Hub for Linux** (рабочее имя репозитория — `victus-suite`)
**Что это:** аналог OMEN Gaming Hub для Linux: подсветка клавиатуры, режимы
производительности, вентиляторы, мониторинг и оверлей (замена Shift+F2).
**Хостинг:** GitHub (публичный репозиторий — обязательно, см. §12.1).
**Текущая локальная папка:** `~/Work/victus-suite` (переименование при создании репо).
**Версия:** 1.1-alpha
**Дата:** 26.09.2026 (обновлено)
**Целевая платформа тестирования:** HP Victus 16-r0xxx, i5-13500H, RTX 4060, ядро 7.2.5-3-omarchy, Omarchy/Arch

---

## 1. Общие сведения

### 1.1. Проблема

В Windows на данном ноутбуке используется OMEN Gaming Hub:
`Shift+F2` открывает оверлей (температуры CPU/GPU, FPS) и переключает режимы
(Comfort / Default / Performance), там же — цвет подсветки клавиатуры,
управление вентиляторами (Auto/Max/Manual) и лимиты питания.

В Linux из этого работает только *частично* и *разрозненно*:
ядро выдаёт `platform_profile`, hwmon-вентиляторы и RAPL/NVIDIA-лимиты,
но **нет единой программы**, которая бы это объединила, и **нет оверлея**.

### 1.2. Текущее состояние (что уже сделано)

| Компонент | Статус |
|---|---|
| `victus-kbd` — запись RGB в EC (`0x08..0x0A`), root | ✅ рабочий прототип, проверен |
| `ColorMaker` — именованные цвета (english), `~/.config/victus-kbd/colors.conf` | ✅ рабочий |
| `Changer` — применение цвета/случайный/выкл | ✅ рабочий |
| `victus_log.py` — общий логгер (уровни, ротация, traceback) | ✅ рабочий, подключён к 3 CLI |
| `victus-report` — сборщик отчёта (система+узлы+логи) | ✅ рабочий |
| Вентиляторы через `/sys/class/hwmon/hwmon7` (`pwm1`, `pwm1_enable`, RPM) | ✅ доступно ядром, не обёрнуто |
| Режимы через `/sys/firmware/acpi/platform_profile` + `power-profiles-daemon` | ✅ доступно, не обёрнуто |
| Оверлей температур/FPS | ❌ |
| Daemon, пресеты, автозапуск, GUI | ❌ |

### 1.3. Ссылки на исследования

- `docs/01-chto-sdelano.md` — как устроен RGB
- `docs/02-audit-sistemy.md` — полный аудит узлов sysfs/WMI этой машины
- `docs/03-podsvetka-rgb.md` — варианты RGB и план поддержки моделей
- `docs/04-ventilyatory.md` — PWM, тайминги 10 с / 120 с / 90 с, риски
- `docs/05-rezhimy.md` — соответствие OMEN ↔ Linux, что крутить
- `docs/06-overlay-i-upravlenie.md` — оверлей, источники данных

---

## 2. Цели и задачи

### 2.1. Цели (Goals)

1. **G1.** Одна программа (`victus`) управляет: подсветкой, вентиляторами,
   режимами питания, лимитами CPU/GPU, мониторингом.
2. **G2.** Работает «из коробки» на **любом дистрибутиве** (Arch, Debian/Ubuntu,
   Fedora, openSUSE) без пересборки ядра — только пакет/скрипт.
3. **G3.** Профили-пресеты (`quiet` / `balanced` / `performance` / `max` +
   пользовательские), применяемые одной командой или хоткеем.
4. **G4.** Оверлей (замена `Shift+F2`): температуры, RPM, FPS, режим,
   с переключением режимов прямо из оверлея.
5. **G5.** Автосохранение состояния после перезагрузки и выхода из сна.
6. **G6.** Цвета клавиатуры — **только английские имена**, произвольные RGB/hex.
7. **G7.** Безопасно: fail-safe на перегреве, whitelist записей, аудит.

### 2.2. Не-цели (Non-goals)

- Не модифицируем ядро и не требуем DKMS (но *поддерживаем* как опцию).
- Не претендуем на Windows/macOS.
- Не разгон (undervolt/разгон ядер) — только штатные лимиты.
- Не эмулируем OMEN Gaming Hub полностью (нет OMEN AI, Booster, Network Priority).

### 2.3. Определения

- **EC** — Embedded Controller, доступ через `/sys/kernel/debug/ec/ec0/io`.
- **Пресет** — именованный набор действий по всем подсистемам.
- **Привилегированный daemon** — сервис под root, единственный пишущий в EC/hwmon.

### 2.4. Стратегия: сначала простое, потом сложное

Продукт = **аналог OMEN Gaming Hub для Linux** (для HP Victus и OMEN).
Порядок работ определяется не «важностью», а **стоимостью входа**:
берём то, что даёт эффект сразу и почти без риска, и только потом то, что
сложно/опасно.

| Фаза | Задача | Сложность | Почему именно так |
|---|---|---|---|
| **A. Свет** ✅ | Цвет/цикл подсветки клавиатуры (`Changer`, `cycle`, `cycle-red`) | низкая | уже работает, видно глазами, нет риска для охлаждения |
| **B. Режимы** | `profile set quiet/balanced/performance` (platform_profile + EPP + `-pl`) | низкая–средняя | sysfs уже есть, ничего не пишем в EC |
| **C. Вентиляторы** | hwmon PWM + кривая + fail-safe | средняя | есть watchdog/тайминги, но риск перегрева |
| **D. Мониторинг + оверлей** | `monitor`, `overlay` (замена Shift+F2) | средняя | только чтение |
| **E. Daemon/GUI/пакеты** | D-Bus, GTK, .deb/.rpm/AUR | высокая | интеграция и дистрибуция |
| **F. Переносимость** | другие модели, LED-class fallback | высокая | после стабилизации ядра |

**Управление питанием (PL1/PL2, EPP, RAPL, `nvidia-smi -pl`) — не стартовая
задача.** Оно было проверено «просто из интереса, работает или нет»
(работает — см. `docs/05`). В фазе B оно применяется **минимумом**: только
`platform_profile` + NVIDIA power limit, без возни с RAPL/thermald.

Правило: **каждая фаза должна заканчиваться работающей командой и записью в
`logs/`**, а не «подготовкой к работе».

---

## 3. Архитектура

```
┌──────────────────────────────────────────────────────────┐
│  CLI: victus ...        GUI (GTK4/Qt)     Hyprland OSD   │
└───────────────┬──────────────────────────────────────────┘
                │  D-Bus (org.victus.Suite)  +  polkit
┌───────────────▼──────────────────────────────────────────┐
│  victusd  (privileged daemon, root)                      │
│  ├─ rgb:       EC 0x08.. / multicolor-leds / WMI         │
│  ├─ fan:       hwmon pwm + curve engine + watchdog 90s   │
│  ├─ profile:   platform_profile + EPP + RAPL + nvidia-smi│
│  ├─ monitor:   coretemp/acpitz/nvme/hp/nvidia readers    │
│  └─ state:     ~/.config/victus/state.json + backup EC   │
└───────────────┬──────────────────────────────────────────┘
                │  libvictus (общая библиотека, Rust/C)
┌───────────────▼──────────────────────────────────────────┐
│  sysfs / WMI / DMI  — автоопределение устройства         │
└──────────────────────────────────────────────────────────┘
```

**Язык:** Rust (рекомендуется: один статический бинарник, легко across-distro)
или Python (быстрее прототип, но тянет зависимость python).

**Разделение прав:**
- `victusd` — root, только он пишет.
- `victus` (CLI), GUI, OSD — user, ходят в D-Bus.
- polkit-действие `org.victus.manage` + правила: admin без пароля,
  group `victus` — с паролем, остальные — отказ.

*Упрощённый MVP-вариант без D-Bus:* один бинарник + `sudoers.d` NOPASSWD
на этот бинарник (см. §11, Этап 0).

---

## 4. Функциональные требования

### 4.1. Модуль RGB (подсветка) — `victus rgb`

| ID | Требование |
|---|---|
| RGB-01 | `victus rgb set <name>` — по имени из палитры; имена только `[a-z][a-z0-9_-]*` |
| RGB-02 | `victus rgb set <r> <g> <b>` и `#RRGGBB` — произвольный цвет |
| RGB-03 | `victus rgb list` — палитра (built-in + пользовательские) |
| RGB-04 | `victus rgb add/remove <name> [rgb]` — CRUD, хранилище `colors.conf` |
| RGB-05 | `victus rgb get` — текущий цвет (чтение EC) |
| RGB-06 | `victus rgb random [group]` — случайный из группы (`pastel`, `neon`, `warm`…) |
| RGB-07 | `victus rgb off` |
| RGB-08 | Эффекты: `breathe`, `rainbow`, `alternate <a> <b>`, `fade <a> <b> [speed]`, `stop` |
| RGB-09 | Яркость: `victus rgb brightness <0-100>` — если узел доступен (EC 0x29 / WMI 0x0D / LED-class) |
| RGB-10 | Автовосстановление последнего цвета после boot/sleep |
| RGB-11 | Бэкап 64 байт EC перед первой записью; `victus rgb restore` |
| RGB-12 | Резервирование через `/sys/class/leds/rgb:*` при наличии (предпочтительный путь) |

**Ограничение:** запись только в известные offset'ы, значения строго 0..255,
lock-файл от параллельных писателей, таймаут записи.

### 4.2. Модуль вентиляторов — `victus fan`

| ID | Требование |
|---|---|
| FAN-01 | `victus fan status` — RPM, PWM, режим (AUTO/MANUAL/MAX), источники датчиков |
| FAN-02 | `victus fan mode auto\|manual\|max` → `pwm1_enable` = 2/1/0 |
| FAN-03 | `victus fan set <pwm> [pwm2]` — только в manual |
| FAN-04 | `victus fan curve <preset|file>` — кривая (точки «температура → pwm») |
| FAN-05 | Кривая по умолчанию: тихая / сбалансированная / агрессивная |
| FAN-06 | Watchdog: ре-примен кривой каждые **90 с** (BIOS timeout 120 с) |
| FAN-07 | **Stagger:** второй вентилятор ставим не раньше чем через **10 с** после первого |
| FAN-08 | **Fail-safe:** CPU ≥ 92 °C или GPU ≥ 83 °C → немедленно `auto` + событие в лог/уведомление |
| FAN-09 | Порог возвращения в кривую: CPU ≤ 80 °C и GPU ≤ 75 °C (гистерезис) |
| FAN-10 | `victus fan max` / `victus fan auto` — мгновенные пресеты |
| FAN-11 | Daemon останавливает управление вентиляторами при suspend/resume |
| FAN-12 | Если `hp_wmi_fan_control_supported()` = false → честный отказ, только `auto/max` |

### 4.3. Модуль режимов питания — `victus profile`

| ID | Требование |
|---|---|
| PROF-01 | `victus profile list` / `get` / `set <name>` |
| PROF-02 | Встроенные: `quiet`, `balanced`, `performance`, `max` |
| PROF-03 | Каждый пресет применяет **набор** действий (см. §4.3.1) |
| PROF-04 | Пользовательские пресеты в `~/.config/victus/profiles.d/*.toml` |
| PROF-05 | Интеграция с `power-profiles-daemon`: если он есть — через него, иначе напрямую `platform_profile` |
| PROF-06 | `victus profile apply-on-battery <name>` / `apply-on-ac <name>` |
| PROF-07 | Хранить и откатывать предыдущее состояние при выходе (`restore-on-exit`) |

#### 4.3.1. Матрица встроенных пресетов

| Действие | `quiet` | `balanced` | `performance` | `max` |
|---|---|---|---|---|
| `platform_profile` | low-power | balanced | performance | performance |
| `energy_performance_preference` | power | balance_performance | performance | performance |
| `intel_pstate/max_perf_pct` | 70 | 100 | 100 | 100 |
| `intel_pstate/no_turbo` | 1 | 0 | 0 | 0 |
| NVIDIA `-pl` (W) | default | default | max (120) | max (120) |
| Fan mode | auto | auto | auto | max |
| Fan curve | тихая | сбалансированная | агрессивная | — |

Отсутствующие узлы пропускаются с предупреждением (не фейл).

### 4.4. Модуль мониторинга — `victus monitor`

| ID | Требование |
|---|---|
| MON-01 | `victus monitor` — вывод CPU/GPU temp, RPM, PWM, power draw, режим, FPS (если есть) |
| MON-02 | `victus monitor --json` — машинный формат (для GUI/OSD) |
| MON-03 | Источники: coretemp, acpitz, nvme, hwmon `hp`, `nvidia-smi`, RAPL |
| MON-04 | Интервал опроса 1–2 с, без root (чтение) |
| MON-05 | `victus monitor watch --on-threshold cpu=90 ...` — колбэки/уведомления |

### 4.5. Модуль оверлея (замена Shift+F2) — `victus overlay`

| ID | Требование |
|---|---|
| OV-01 | `victus overlay toggle` — окно поверх всех окон (layer-shell для Wayland, X11 fallback) |
| OV-02 | Показывает: CPU °C, GPU °C, CPU/GPU %, RPM×2, текущий пресет, FPS |
| OV-03 | Клик/клавиша внутри оверлея переключает пресет (как в OMEN) |
| OV-04 | Горячая клавиша: `Shift+F2` (проброс в `hyprland.conf` / `sway` / `gnome`) |
| OV-05 | FPS берётся из MangoHud IPC, если игра запущена с MangoHud; иначе поле скрыто |
| OV-06 | Обновление ≤ 1 Гц, потребление CPU < 1% в простое |
| OV-07 | `--compact` режим (только значения) и `--hud` (полный) |

### 4.6. Модуль профилей по событиям — `victus rules`

| ID | Требование |
|---|---|
| RULE-01 | Правила вида `when ac→performance / battery→quiet` |
| RULE-02 | Привязка профиля к приложению (`when game:cs2 → performance`) |
| RULE-03 | `victus rules enable/disable/list` |
| RULE-04 | Обнаружение игры: активное окно (Hyprland IPC) / запуск через `mangohud` |

---

## 5. Интерфейсы

### 5.1. CLI

```
victus <module> <command> [options]

victus rgb set pink | 255 105 180 | "#ff69b4"
victus rgb list | add NAME R G B | rm NAME | get | off | brightness 80
victus fan status | mode manual | set 180 | curve gaming | max | auto
victus profile list | get | set performance
victus monitor [--json] [--interval 1]
victus overlay toggle | start | stop
victus rules list | add "..."
victus doctor          # диагностика: что доступно на этой машине
victus report [--with-ec]   # собрать логи+состояние в один файл (bug report)
victus log tail [-n N] | show | clear
victus daemon start|stop|status|logs
```

`victus doctor` — обязательный командный инструмент: печатает таблицу
доступных узлов (RGB-бэкенд, hwmon, platform_profile, nvidia, mango) и что
недоступно и почему.

### 5.2. D-Bus

```
Сервис:  org.victus.Suite       (system bus)
Объект:  /org/victus/Suite
Интерфейсы:
  org.victus.RGB       SetColor(r,g,b), SetNamed(name), GetColor(), ListColors()
  org.victus.Fan       GetStatus(), SetMode(mode), SetPwm(pwm), SetCurve(id)
  org.victus.Profile   List(), Get(), Set(name)
  org.victus.Monitor   Snapshot() → a{sv}, Subscribe(interval)
  org.victus.Overlay   Toggle()
Сигналы: ColorChanged, ProfileChanged, ThresholdExceeded(name, temp)
polkit:  org.victus.manage
```

### 5.3. Конфигурация

```
/etc/victus/victus.toml            # системные умолчания
~/.config/victus/config.toml       # пользователь
~/.config/victus/colors.conf       # именованные цвета (совместимо с ColorMaker)
~/.config/victus/profiles.d/*.toml # пользовательские пресеты
~/.config/victus/curves.d/*.toml   # кривые вентиляторов
~/.config/victus/rules.toml        # правила
~/.local/state/victus/state.json   # последнее применённое состояние
~/.local/state/victus/ec-backup.bin# бэкап EC (64 байта)
```

Формат пресета (пример):

```toml
# ~/.config/victus/profiles.d/turbo.toml
name = "turbo"
[platform_profile]
value = "performance"
[epp]
value = "performance"
[nvidia]
power_limit_w = 120
[fan]
mode = "max"
```

---

## 6. Требования к совместимости

### 6.1. Дистрибутивы

| Дистрибутив | Пакет | Тест |
|---|---|---|
| Arch/Omarchy | `victus-suite` (PKGBUILD, AUR) | ✅ первичный |
| Ubuntu/Debian | `.deb` | Обязателен |
| Fedora | `.rpm` | Обязателен |
| openSUSE | `.rpm` (obs) | Желателен |
| Остальные | AppImage / `install.sh` (tar.gz) | Резерв |

Зависимости: только libc + `nvidia-smi` (опционально) + `power-profiles-daemon`
(опционально). Никаких DE-зависимостей у демона.

### 6.2. Ядро / возможности

| Возможность | Минимум | Fallback |
|---|---|---|
| RGB | `ec_sys write_support=1` | `/sys/class/leds/rgb:*` (когда влит патч) |
| Фаны | `hp-wmi` с hwmon (≈6.17+) | DKMS-модуль; иначе только auto/max |
| Режимы | `platform_profile` (5.2+) | WMI `0x1A` |
| NVIDIA | драйвер с `nvidia-smi` | без лимитов |
| Оверлей | MangoHud (опц.) | без FPS |

`victus doctor` обязан печатать это в виде таблицы доступности.

### 6.3. Матрица моделей (приоритеты)

| P | Модель | Ожидаемый бэкенд RGB |
|---|---|---|
| P0 | HP Victus 16-r0xxx (эта) | EC 0x08 ✅ проверено |
| P0 | HP Victus 16-s0xxx | EC + hwmon fan (есть upstream-патчи) |
| P1 | HP Victus 15 fa/fb | EC, свой layout |
| P1 | HP OMEN 16/17 | EC thermal 0x95 + RGB |
| P2 | Любой HP с multicolor LED | `/sys/class/leds/rgb:*` |
| P3 | ASUS (asus-wmi) / Lenovo (ideapad) / Dell (alienware-wmi) | штатные драйверы |

Автодетект: `dmidecode`/`/sys/class/dmi/id/{product_name,board_name,product_sku}`
→ таблица `device_profiles.toml` (включается в пакет).

---

## 7. Нефункциональные требования

### 7.1. Безопасность

- **S-01** В EC пишется только whitelist offset'ов (RGB: 0x08..0x0A). Любой
  другой poke запрещён на уровне кода.
- **S-02** Перед первой записью — бэкап 64 байт EC; `victus rgb restore`.
- **S-03** Писать только при `euid==0`; проверка в daemon, не в CLI.
- **S-04** D-Bus-вызовы защищены polkit; без прав — отказ.
- **S-05** Lock-файл (`/run/victus.lock`) от параллельных записей.
- **S-06** Лог действий (`journalctl -u victusd`), без записи секретов.
- **S-07** Fan fail-safe (FAN-08) не может быть отключён.
- **S-08** Нет auto-start записи в EC при `--dry-run`.

### 7.2. Надёжность

- **R-01** Daemon переживает `suspend/resume` (systemd sleep hooks).
- **R-02** При падении демона вентиляторы остаются в AUTO (последнее
  подтверждённое состояние не «зависает» в manual > 120 с — watchdog).
- **R-03** `systemd` unit с `Restart=on-failure`, `WatchdogSec=30`.
- **R-04** Никаких segfault'ов при недоступных узлах — каждая операция
  возвращает `unsupported` вместо падения.

### 7.3. Производительность

- Daemon: RSS < 30 MB, CPU < 1% при опросе 1 с.
- Overlay: CPU < 1%, отрисовка ≤ 1 Гц.
- CLI запуск < 100 мс.

### 7.4. Локализация

- Русский и английский интерфейсы CLI/GUI.
- **Имена цветов — только английские** (requirement G6): валидация `[a-z][a-z0-9_-]{0,31}`.

### 7.5. Тестируемость

- Unit-тесты на парсинг конфигов, кривых, палитры, валидацию имён.
- Интеграционные тесты на «mock-sysfs» (фикстура каталога с фейковыми файлами).
- Smoke-тест на реальной машине: `victus doctor` exit code = 0.

### 7.6. Логирование и диагностика

Цель: **при любой ошибке должно быть понятно, что произошло, без повторения
действий вслепую.** Один файл = полная картина для баг-репорта.

| ID | Требование |
|---|---|
| LOG-01 | Единый лог CLI/демона: `~/.local/state/victus/victus.log` (XDG state). Демон дополнительно пишет в journald (`journalctl -u victusd`). |
| LOG-02 | Формат строки: `ISO8601 с таймзоной LEVEL pid=… euid=… tool: message`. Обязателен `euid` — сразу видно, что упало из-за отсутствия root. |
| LOG-03 | Уровни: `debug/info/warn/error`. Уровень = env `VICTUS_LOG` (по умолчанию `info`). |
| LOG-04 | Каждая запись/изменение логируется: команда, аргументы, что читалось, что записалось, результат (readback), код возврата. |
| LOG-05 | **Исключения**: полный traceback в лог (`|`-продолжение строк), а в stderr — короткое сообщение + путь к логу. |
| LOG-06 | Парсинг конфигов логирует `file:line: ошибка` для каждой битой строки (не «тихое» пропускание). |
| LOG-07 | Ротация: >512 KiB → `victus.log.1..5`, старые удаляются. Никакого бесконечного роста. |
| LOG-08 | `victus report [--with-ec]` собирает в **один файл**: систему (uname, DMI, модули), наличие узлов (LED/EC/hwmon/platform_profile/NVIDIA), снимки фанов/температур/профилей, dmesg по `hp|wmi|ec`, tail лога, `colors.conf`, опционально дамп EC. |
| LOG-09 | `victus log tail/show/clear` — просмотр и очистка. |
| LOG-10 | Daemon: `journalctl -u victusd -b` + `victus doctor` = обязательный минимум в баг-репорте. |
| LOG-11 | Каждая **запись в EC** логируется с `before → after` и пометкой offset'а; несовпадение readback — `warn` (EC клампит) или `error` (запись не применилась). |
| LOG-12 | Каждое **изменение пресета/вентилятора** — отдельная запись с указанием целевых sysfs-путей и значений. |
| LOG-13 | Fail-safe (перегрев → AUTO) логируется как `error` + порог + температура, и дублируется сигналом/уведомлением. |
| LOG-14 | Лог **не содержит** секретов; серийный номер при экспорте отчёта маскируется по флагу `--anonymize`. |
| LOG-15 | `victus report` работает без root (root-части опциональны и не роняют отчёт). |

**Уже реализовано (прототип):** `~/.local/bin/victus_log.py` — общий модуль
уровней/ротации/traceback, подключён к `victus-kbd`, `ColorMaker`, `Changer`;
`~/.local/bin/victus-report` — сборщик отчёта.

---

## 8. Этапы (Milestones)

### Этап v1.1-alpha — TUI Framework & Basic KBD Control ✅ выполнен (26.09.2026)
- [x] TUI на **Textual** (`bin/victus_tui` + `bin/tui/`): вкладка «Подсветка»,
      вкл/выкл, 48 пресетов, слайдеры HSV, свотч + `rgb()/#hex/hsv()`,
      «Применить»/«Копировать hex»/«Сохранить как имя», эффект Cycle со
      скоростью, Старт/Стоп, статус-строка, состояния в `state/last_state.json`
- [x] Базовое управление подсветкой из TUI — запись **только** через
      `victus-kbd` (TUI = обёртка над CLI, параллельной логики нет)
- [x] Локализация TUI (ru/en, ключи `tui.*`), headless-тесты 21/21
- [x] Живой тест пользователем: **базовый функционал работает**
- Статус альфы: функционал рабочий, визуальная часть и UX требуют
  переработки → этап v1.2

### Этап v1.2 — Material Design & Animation Overhaul (следующий)
- [ ] Material Design **3** стиль интерфейса (цветовые токены, типографика)
- [ ] Скруглённые рамки/карточки вместо «топорного» вида
- [ ] **Работающие слайдеры с поддержкой мыши/драга** (сейчас клик по
      слайдеру выделяет текст вместо перетаскивания — критичный UX-баг)
- [ ] Плавные индикаторы и анимации переходов
- [ ] Пересмотр плотности компоновки (заголовки секций, отступы, кнопки)

### Этап 0 — MVP (1–2 дня) ✅ частично готово
- [x] `victus-kbd` (EC RGB), `ColorMaker`, `Changer`
- [x] общий логгер `victus_log.py` (уровни, ротация, traceback) + `victus-report`
- [ ] `victus rgb` — объединить три команды в один CLI
- [ ] `victus log tail/show/clear`
- [ ] автозапуск цвета (systemd user unit / omarchy hook)
- [ ] `sudoers.d` NOPASSWD для одного бинарника (или polkit)
- [ ] `victus doctor` v1

### Этап 1 — Fan + Profile (3–5 дней)
- [ ] обёртка над hwmon PWM: `fan mode/set/curve/status`
- [ ] curve engine + watchdog 90 s + stagger 10 s + fail-safe
- [ ] `profile set` с матрицей §4.3.1
- [ ] systemd system unit `victusd` (fan watchdog только)

### Этап 2 — Daemon + D-Bus (1 неделя)
- [ ] `victusd` с D-Bus API + polkit
- [ ] state persistence + sleep/resume hooks
- [ ] journald-интеграция + `victus log` + `victus report` в daemon-версии
- [ ] пакеты: AUR, .deb, .rpm, install.sh

### Этап 3 — Monitor + Overlay (1 неделя)
- [ ] `victus monitor [--json]`
- [ ] `victus overlay` (layer-shell, GTK4/LayerShell или egui + gtk-layer-shell)
- [ ] интеграция MangoHud FPS, хоткей Shift+F2

### Этап 4 — GUI + правила (1–2 недели)
- [ ] GTK4 приложение (вдохновение: `victus-control` Batuhan4)
- [ ] `victus rules` (AC/battery, per-app)
- [ ] расширение палитры/эффектов RGB, 4-зоны

### Этап 5 — Переносимость (ongoing)
- [ ] таблица `device_profiles.toml` на 10+ моделей HP
- [ ] fallback на `rgb:*` LED-class
- [ ] ASUS/Lenovo бэкенды (P3)

---

## 9. Критерии приёмки

1. На HP Victus 16-r0xxx: `victus rgb set pink` меняет цвет; после reboot
   цвет восстанавливается автоматически.
2. `victus fan curve gaming` поднимает вентиляторы до заданных RPM под
   нагрузкой, при 92 °C уходит в AUTO и логирует событие.
3. `victus profile set performance` меняет `platform_profile`, EPP и
   NVIDIA power limit одной командой; `quiet` возвращает тишину.
4. `victus overlay toggle` показывает CPU/GPU температуры и RPM; с MangoHud — FPS;
   переключение пресета из оверлея работает.
5. `victus doctor` на чужом дистрибутиве (Ubuntu 24.04, Fedora 42) ставится
   пакетом и корректно сообщает, что недоступно, **не падая**.
6. Нет записи в EC вне whitelist; `victus rgb restore` возвращает исходное.
7. Любая ошибка CLI: в stderr — короткое сообщение + путь к логу, в логе —
   `file:line`/traceback и контекст (`euid`, аргументы, sysfs-значения).
8. `victus report` на несработавшей машине даёт файл, по которому
   восстанавливается причина (достаточно для диагностики без перезапуска).
9. Лог ротируется и не превышает 512 KiB + 4 архива.
10. Линт/тесты: `cargo clippy && cargo test` (или `ruff`/`mypy` для Python) — зелёные.

---

## 10. Риски и митигации

| Риск | Влияние | Митигация |
|---|---|---|
| Запись в EC повреждает контроллер | высокое | whitelist offset'ов, бэкап, dry-run, только своя ревизия |
| Старое ядро без hwmon-fan | среднее | `doctor` + DKMS-опция + честный отказ |
| Патч multicolor LED не влит годами | среднее | EC-путь остаётся основным |
| thermald/PPD конфликтуют с нашими записями | среднее | работать через PPD API, не против |
| Перегрев из-за ручной кривой | высокое | FAN-08 fail-safe, гистерезис, AUTO по умолчанию |
| Разные layout RGB по ревизиям | среднее | таблица по DMI + `victus rgb probe` (осторожно) |
| NVIDIA proprietary vs open module | низкое | обнаружение через `nvidia-smi` |
| Wayland-only окружение | низкое | layer-shell + X11 fallback |

---

## 11. Открытые вопросы

1. **Права:** polkit+D-Bus (правильно) или `sudoers.d` NOPASSWD (быстро)? → MVP: sudoers, далее polkit.
2. **Язык:** Rust (прод) vs Python (быстрый MVP)? → прототип Python уже есть, продакшен — Rust.
3. **GUI:** GTK4 (как victus-control) vs TUI vs только OSD? 
4. **Яркость подсветки:** подтвердить ли EC `0x29` и/или WMI event `0x0D`.
5. **Сохранность цвета в EC** — проверить после reboot/sleep (задача: замерить).
6. Распространять ли DKMS-модуль для старых ядер (нарушает G2 «без пересборки») или считать опцией.
7. Нужен ли профиль «boost на N минут» (как «Max fan» в OMEN) как отдельная команда.

---

## 12. Организация проекта: всё в одной папке

Требование: **разработка ведётся агентом, весь результат — в одном каталоге.**
Никаких файлов «по всему дому»: код, конфиги, логи, отчёты, документация — в одном месте.

### 12.1. Хостинг (GitHub — обязательно)

- Репозиторий **публичный**, имя: `victus-suite`
  (описание: *OMEN Gaming Hub for Linux — HP Victus/OMEN keyboard RGB,
  fan control, power profiles, overlay*).
- Всё, что попадает в git: `bin/`, `config/*.conf`, `docs/`, `TZ.md`,
  `README.md`, `install.sh`, `LICENSE` (MIT), `.gitignore`.
- **В git НЕ попадает:** `logs/`, `state/` (отчёты/логи — приватные,
  прикладываются к issue вручную), `__pycache__/`, `*.pyc`,
  `config/*local*` (персональные цвета — по желанию).
- Каждая фаза = отдельный коммит/тег (`v0.1-rgb`, `v0.2-profiles`, …).
- README на GitHub = тот же `README.md` в корне (он же быстрый старт).
- Описание/теги репо: `linux`, `hp`, `victus`, `omen`, `rgb`, `fan-control`,
  `acpi`, `hwmon`, `wayland`.

```bash
git init
git add README.md TZ.md install.sh LICENSE .gitignore bin config docs
git commit -m "v0.1: keyboard RGB (EC) + ColorMaker/Changer + cycle + docs"
gh repo create victus-suite --public --source=. --remote=origin --push
```

> `gh` на машине есть, но **не авторизован** — нужен `gh auth login`.

```
victus-suite/
├── TZ.md                 это задание
├── README.md             быстрый старт
├── install.sh            ./install.sh [--remove] → симлинки в ~/.local/bin
├── bin/                  исполняемые файлы (сюда «падают» все новые команды)
│   victus-kbd  ColorMaker  Changer  victus-report  victus_log.py
├── config/               всё пользовательское (colors.conf, profiles.d/, curves.d/)
├── logs/                 victus.log (+ .1..5), журналы демона, debug-трейсы
├── state/                report-*.txt, state.json, ec-backup.bin
└── docs/                 01..06 исследование (и дальнейшие заметки)
```

| Правило | Реализация |
|---|---|
| PRJ-01 | Все новые команды кладутся **только** в `bin/` |
| PRJ-02 | Все логи пишутся **только** в `logs/` (`victus_log.log_dir()`) |
| PRJ-03 | Все отчёты/снятое состояние — в `state/` (`victus-report`) |
| PRJ-04 | Всё пользовательское — в `config/` |
| PRJ-05 | Путь определяется по местоположению скрипта (`realpath`), а не по `$HOME` — симлинк из `~/.local/bin` работает и указывает в проект |
| PRJ-06 | Override'ы: `VICTUS_LOG_DIR`, `VICTUS_STATE_DIR`, `VICTUS_CONFIG_DIR`, `VICTUS_LOG` (уровень) |
| PRJ-07 | Внешние команды не требуют установки в систему: `./install.sh` только симлинки |
| PRJ-08 | Демон/пакеты в релизе используют XDG (`~/.local/state/victus`), проектная раскладка — режим разработки |

**Автономность агента:** агент сам создаёт структуру, сам пишет логи в `logs/`,
сам генерирует `state/report-*.txt` при проблемах, сам правит `docs/` и этот `TZ.md`.
Пользовательская входная точка одна: корень проекта.

Состояние на момент написания: раскладка реализована, `install.sh` работает,
логи/отчёты уже в проектной папке.

---

## 13. Приложение A. Быстрая шпаргалка (уже работает)

```bash
# цвет
sudo ~/.local/bin/victus-kbd pink
Changer list
ColorMaker add mycolor 30 144 255 && Changer mycolor

# режим (аналог Comfort/Performance в OMEN)
powerprofilesctl set performance|balanced|power-saver
echo performance | sudo tee /sys/firmware/acpi/platform_profile

# вентиляторы
cat /sys/class/hwmon/hwmon7/fan1_input /sys/class/hwmon/hwmon7/fan2_input
echo 1 | sudo tee /sys/class/hwmon/hwmon7/pwm1_enable   # manual
echo 180 | sudo tee /sys/class/hwmon/hwmon7/pwm1
echo 2 | sudo tee /sys/class/hwmon/hwmon7/pwm1_enable   # auto

# лимиты
sudo nvidia-smi -pl 120
echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference

# мониторинг
sensors
nvidia-smi
```

---

## 14. Версия 1.0.0-beta: зафиксированная архитектура и переход к приложению

> Редакция 2026-09-29. Источник версии — файл `VERSION`.
> Следующий этап упаковки/дистрибуции — `ROADMAP.md` (R1…R5).

### 14.1. Что зафиксировано в 1.0.0-beta

| Блок | Файл | Суть |
|---|---|---|
| Ядро (EC, права, движок) | `bin/tui/core.py` | `probe_access()` → вердикт `direct`/`sudo`/`none`; `needs_sudo`, `_with_priv`, `ec_module_ok`, `access_hint` (подсказка про modprobe только если модуля реально нет); `delay_for_speed(speed) = 0.25/speed` (clamp 0.05…2.0) — **направление совпадает с фазой синуса**; `Engine`/`local_apply`/`local_effect_start` |
| Вкладка подсветки | `bin/tui/kbd_tab.py` | пресеты, пикер, эффекты, `kill_loop()` (останавливает цикл через CLI/демон), `set_calm()` (покой/бой), `_rebuilding` + `restore_running()` (пересборка виджета при смене языка не гасит эффект) |
| Экран и кнопка языка | `bin/tui/screens.py` | макет Bento 960×540 (`#shell` → три панели), `#titlerow` + `#lang`, `toggle_language()` (пишет `config/locale`, пересоздаёт дерево) |
| ASCII-слайдеры и волна | `bin/tui/slider.py` | слайдеры (клик/колесо, без выделения текста); `SineWave`: лерп `_amp_k`/`_period_div` от скорости (0.06/0.05 за тик 0.12 c), `energy` 0→1, **спокойный режим** (амплитуда `max(base*amp_k*(0.10+0.90e), 0.55)`, ось в цвет), **плавное переливание** (`_step_target` + доездка ≤0.04/тик по кратчайшей дуге) |
| Запись в EC | `bin/victus-kbd` | `ec_ready()`, гейт «euid!=0 → работаем, если ec_ready() или cmd==stop»; `cycle --delay ≥ 0.05` |
| Фон | `bin/victusd` | unix-сокет `$XDG_RUNTIME_DIR/victus-suite-<uid>.sock`, счётчик `k` идёт с той же периодичностью, что цикл клавиатуры; `--verbose`, `--quit`; автостарт из `victus_tui` |
| Трей | `bin/victus-tray` | AyatanaAppIndicator3: открыть окно / старт-стоп / выход; `victus_tui --tray` |
| Точка входа | `bin/victus_tui` | без флагов — в терминале; `--window` — float 960×540 (foot, запасной kitty); `--tray` — только демон+трей |

**Жёсткого автозапуска нет.** `victusd` поднимается, когда нужен, и умирает
по `--quit`/закрытию последнего клиента; автозапуск при входе в систему —
это R3 в `ROADMAP.md` (systemd --user), а не текущее поведение.

### 14.2. Ключевые договорённости (не ломать)

1. **TUI = тонкая обёртка над CLI.** Любая запись в EC идёт через
   `victus-kbd` (или `core._with_priv`), никакой параллельной логики записи.
2. **Права проверяются по факту** (`probe_access`), а не «всегда sudo».
   Если изменился гейт в `victus-kbd` — синхронно править `core.probe_access`.
3. **Скорость одна на всё:** `delay_for_speed` управляет и циклом клавиатуры,
   и локальным `auto_flow`. Менять направление только вместе с тестами
   `daemon_smoke` / `daemon_tui_smoke`.
4. **`kill_loop()` перед каждым новым действием**, который не должен конфликтовать
   с бегущим циклом; `set_calm(True)` — только когда эффект точно остановлен.
5. **Состояние** — `state/last_state.json` (единственный источник правды,
   демон и TUI читают его одинаково). Язык — `config/locale` / `VICTUS_LANG`.
6. **Тесты последовательные:** сьюты делят сокет и `last_state.json`,
   параллельный запуск даёт ложные падения. Перед прогоном — `killer.py`
   (`/tmp/opencode/v2/`), после — сброс `state/last_state.json` в дефолт.

### 14.3. Порядок входа нового агента

1. `START_DEVELOPMENT.md` (правила §0, состояние §2, roadmap §4).
2. `PROGRESS_LOG.md` → «ТЕКУЩИЙ СТАТУС» + верхняя запись.
3. `ROADMAP.md` — что делать в этом этапе (R1…R5).
4. Только потом код: `bin/tui/core.py` → `kbd_tab.py` → `slider.py` → `screens.py`.
5. Проверка после любой правки: 6 смоук-сьютов (`/tmp/opencode/v2/`),
   итог — 186 проверок. Фон чист, `state/last_state.json` — дефолтный.
