# 06. Оверлей (замена Shift+F2) и мониторинг

## Что показывает оверлей OMEN (Windows)

- Температура CPU / GPU (цветовые пороги)
- FPS, frame time, 1% low
- Загрузка CPU/GPU/RAM, частоты, RPM
- Переключатель режима и вентилятора

В Linux **готового аналога с переключением режимов нет**. Есть два слоя:

### 1. Оверлей в игре (FPS/температуры) — готовое

| Инструмент | Что умеет | Статус |
|---|---|---|
| **MangoHud** | FPS, CPU/GPU temp, usage, графики, накладка | не установлен, ставится `pacman -S mangohud` |
| **Gamescope** | встроенный HUD | уже может быть в compositor |
| **overlayfs-виджет Hyprland** | свой OSD в bar | писать самим |

MangoHud: `MANGOHUD_CONFIG=cpu_temp,gpu_temp,fps,power` + хоткей
`Shift+F2` можно пробросить в `hyprland.conf` для показа/скрытия.

### 2. Системный виджет/приложение — писать самим

Данные уже доступны без root:

```bash
# температуры
awk '{print $1/1000}' /sys/class/hwmon/hwmon8/temp1_input   # CPU °C
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw --format=csv,noheader
# RPM
cat /sys/class/hwmon/hwmon7/fan1_input /sys/class/hwmon/hwmon7/fan2_input
# FPS из MangoHud: сокет /tmp/mangohud  или mangojud IPC
```

Плюс `powerprofilesctl get` для текущего режима.

## Где брать FPS на Linux

- MangoHud IPC / `mangohud` включается на игру через `mangohud %command%`.
- `gamescope` HUD.
- Для Wayland/Hyprland — свой OSD поверх (layer-shell), обновление 1 Гц.

## Горячие клавиши (привязка к Hyprland)

```conf
# ~/.config/hypr/hyprland.conf
bind = SHIFT, F2, exec, victus-overlay toggle      # наше будущее
bind = SHIFT, F3, exec, victus-kbd-profile performance
```

Omarchy уже имеет `omarchy-brightness-keyboard` (яркость по LED-class) —
на этой машине он не находит устройство, т.к. `*kbd_backlight*` нет.

## Сравнение: что закрыто, что нет

| Функция OMEN | Linux-аналог | Наш статус |
|---|---|---|
| Цвет подсветки | EC 0x08 | ✅ работает |
| Яркость подсветки | WMI 0x0D / EC 0x29 | ❌ не исследовано |
| Comfort/Balanced/Performance | `platform_profile` | ✅ работает |
| Fan Auto/Max/Manual | hwmon `pwm1_enable` | ✅ работает (root) |
| Fan curve (ручная) | hwmon + watchdog | 🟡 не написан daemon |
| Оверлей температур | MangoHud | 🟡 не установлен |
| Оверлей + переключатель | своя программа | ❌ в ТЗ |
| CPU/GPU power limit | RAPL + `nvidia-smi -pl` | 🟡 есть sysfs, нет UI |
| Профили на игру | наш daemon + автостарт | ❌ в ТЗ |
| Сохранность после перезагрузки | systemd unit | ❌ в ТЗ |

Вывод: **драйверный уровень почти весь готов ядром**, не хватает
userspace-программы, которая всё это соберёт в один интерфейс.
