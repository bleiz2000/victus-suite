# 03. Подсветка RGB: текущее решение и путь к продукту

## Варианты управления RGB на HP (по убыванию «правильности»)

### A. LED multicolor через hp-wmi (upstream) — СТАТУС: не влито

Серия патчей `platform/x86: hp-wmi: Add multicolor LED support for HP keyboard
backlight` (v6…v9, автор — Коненко Андрей). Даёт:

```
/sys/class/leds/rgb:kbd_backlight/...   (led-multicolor, per-zone)
```

То есть обычный Linux-механизм: `brightnessctl`, `ledtrig`, без root-дампов EC.
Плюс WMI event `HPWMI_BACKLIT_KB_BRIGHTNESS = 0x0D` на яркость.

**Что делать:** отслеживать линийку `platform/x86` (ожидается 6.19/6.20+);
как только влито — перейти на sysfs, а EC-путь оставить fallback'ом.

### B. EC-запись (реализовано) — СТАТУС: работает

Плюсы: работает уже сейчас, без пересборки ядра, один python-скрипт.
Минусы: root, один offset, нет яркости, риск, нет зон, хрупко к ревизиям BIOS.

Формат: `EC[0x08]=R, EC[0x09]=G, EC[0x0A]=B`, диапазон 0..255
(на части ревизий максимум `0xE4`).

### C. WMI query напрямую (сервис-уровень) — СТАТУС: не исследовано

У OMEN Gaming Hub в Windows цвет и яркость шлются в BIOS через
`HPWMI_BIOS_GUID`. Можно воспроизвести `hp_wmi_perform_query(...)` из
user-space через `/sys/bus/wmi/devices/<GUID>/` — но kernel `hp-wmi`
query-интерфейс в user-space **не отдаёт** (нужен своя реализация через
`ioctl` на WMI-char-dev либо модуль). Оценить на этапе R&D.

### D. OpenRGB — СТАТУС: не подходит

OpenRGB не умеет EC/WMI-клавиатуры HP; работает только с USB-контроллерами.

## Что нужно доделать, чтобы стало «программой»

1. **Автозапуск цвета после загрузки/сна**
   - systemd user unit или hook в `~/.config/omarchy/hooks/`,
   - либо state-файл + `ExecStartPost` в системном сервисе.
2. **Права без пароля**
   - вариант 1: polkit-правило + маленький privileged daemon (dbus),
   - вариант 2: udev-правило, дающее группе `video` запись в
     `/sys/kernel/debug/ec/ec0/io` (debugfs всё равно 0700 → нужен mount с
     `mode=755` или отдельный service),
   - вариант 3: `sudoers.d` с NOPASSWD ровно на один бинарник (самый простой).
3. **Зоны**: для 4-зонных OMEN — 12 байт (или свой layout), определять по DMI.
4. **Эффекты**: breathe/rainbow/alternate — цикл в userspace (как в
   RGB_Tuner4Victus) либо в daemon'е.
5. **Яркость**: исследовать EC-байт `0x29` и WMI event `0x0D`.
   *Сделано 2026-10-01 программно*: в TUI есть уровень 0..100
   (`core.apply_brightness`) — цвет масштабируется перед записью в EC,
   петля идёт через `colors_for_state`, живая запись без Apply (0.4 с
   debounce, как у фенов). Аппаратные байты (0x29 / 0x0D) остаются
   R&D: подтверждённого байта яркости нет, WMI-событие в Linux не
   пробрасывается.
6. **Безопасность**:
   - перед записью — резервная копия 64 байт EC в state-файл;
   - whitelist только своих offset'ов, никаких произвольных poke;
   - lock-файл от параллельных записей.

## Существующие проекты (для референса)

| Проект | Подход |
|---|---|
| `najisheheem05/RGB_Tuner4Victus` | Python, EC offset 0x08, эффекты |
| `najisheheem05/victus-tuner` | Rust, то же самое |
| `Batuhan4/victus-control` | GTK4 + backend, фаны + RGB, требует hp-wmi fork |
| `kadir-y/victus16-keyboard-ui` | GTK4, AUR `victus16-keyboard-ui` |
| `hp-wmi` upstream patch v9 | multicolor LED — целевой путь |

## Матрица поддержки (план продукта)

| Платформа | Метод RGB | Приоритет |
|---|---|---|
| HP Victus 16 (13/14 gen) | EC 0x08 | P0 — уже работает |
| HP Victus 15 fa/fb | EC (свой layout) | P1 |
| HP OMEN 16/17 | EC 0x95 thermal + RGB | P1 |
| Прочие HP с multicolor LED | `/sys/class/leds/rgb:*` | P0 как только влито |
| ASUS (asus-wmi)/Lenovo/MSI/Dell | свои драйверы (asusctl, ideapad, alienware-wmi) | P2 |
| Универсальный | открытый конструктор драйверов по DMI | P3 |
