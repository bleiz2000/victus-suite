# 02. Аудит системы (HP Victus 16-r0xxx, снято 25.09.2026)

## Оборудование

| Параметр | Значение |
|---|---|
| Модель | HP Victus by HP Gaming Laptop 16-r0xxx |
| CPU | 13th Gen Intel Core i5-13500H (20 потоков) |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU + iGPU |
| Драйвер NVIDIA | 610.57.04 (open kernel module) |
| Ядро | 7.2.5-3-omarchy |
| Платформенные драйверы | `hp_wmi`, `hp_bioscfg`, `wmi_bmof` |
| ОС | Omarchy (Arch), Hyprland |

## Клавиатура / LED

```
/sys/class/leds:  lan, hda::mute, capslock/numlock/scrolllock/compose/kana
/sys/class/leds/*kbd_backlight*  → НЕТ
/sys/class/keyboard_backlight    → НЕТ
```

Контроллер RGB доступен только через EC (`/sys/kernel/debug/ec/ec0/io`).

## Вентиляторы — УЖЕ ЕСТЬ в ядре

```
/sys/class/hwmon/hwmon7/name = hp        (driver: hp-wmi)
  pwm1       = 96      (rw)
  pwm1_enable= 2       (rw)   0=MAX, 1=MANUAL, 2=AUTO
  pwm2       = 109     (rw)
  fan1_input = 2200    (ro, RPM)   CPU fan
  fan2_input = 2500    (ro, RPM)   GPU fan
```

`pwm2_enable` отсутствует — режим общий для обоих каналов (так устроено
`hp-wmi` upstream: `HWMON_CHANNEL_INFO(pwm, ENABLE|INPUT, INPUT)`).

Драйвер сам держит состояние (keep-alive work, таймаут ~120 с), но **периодический
re-apply всё равно рекомендуется** (см. docs/04).

## Режимы производительности

```
/sys/firmware/acpi/platform_profile            = low-power
/sys/firmware/acpi/platform_profile_choices    = low-power balanced performance
power-profiles-daemon: active
  * power-saver / balanced / performance   (CpuDriver=intel_pstate, PlatformDriver=platform_profile)
thermald: active
```

Т.е. три режима = ровно Comfort / Default / Performance из OMEN Gaming Hub.

## Телеметрия

| Источник | Что даёт |
|---|---|
| `/sys/class/hwmon/hwmon8` (`coretemp`) | Package id 0, Core 1..24 (temp1..temp25) |
| `/sys/class/hwmon/hwmon1` (`acpitz`) | temp1/temp2 (ACPI зона) |
| `/sys/class/hwmon/hwmon3` (`nvme`) | 3 точки NVMe |
| `nvidia-smi` | GPU temp, power draw, power limit |
| `/sys/class/powercap/intel-rapl*` | RAPL power/energy CPU |
| `/sys/class/hwmon/hwmon7` (`hp`) | RPM обоих вентиляторов |

## Управление питанием CPU/GPU

```
/sys/devices/system/cpu/intel_pstate/status = active
  есть: max_perf_pct, min_perf_pct, no_turbo, hwp_dynamic_boost
  energy_performance_preference (cpu0) = power
/sys/class/drm/card2/gt_max_freq_mhz      = есть (частота iGPU)
nvidia-smi: power.min_limit=5W, power.max_limit=120W
             текущий limit=40W, default/requested=80W, max SM clock=3105MHz
```

## Установлено из полезного

`lm_sensors` (`sensors`), `power-profiles-daemon`, `thermald`, `brightnessctl`.
**Нет**: mangohud, psensor, auto-cpufreq, какого-либо omen/victus-туллина.

## WMI-интерфейсы на машине (18 GUID)

```
95F24279-4D7B-4334-9387-ACCDC67EF61C   HPWMI_EVENT_GUID   (hotkeys)
5FB7F034-2C63-45E9-BE91-3D44E2C707E4   HPWMI_BIOS_GUID    (query/write)
+ 16 системных GUID
```

Доступные из драйвера query-кода (`hp-wmi.c`):

```
0x11 FAN_SPEED_GET          0x10 FAN_COUNT_GET       0x1A SET_PERFORMANCE_MODE
0x26 FAN_SPEED_MAX_GET      0x27 FAN_SPEED_MAX_SET   0x29 SET_POWER_LIMITS
0x21 GET_GPU_THERMAL_MODES  0x22 SET_GPU_THERMAL_MODES
0x2D VICTUS_S_FAN_GET       0x2E VICTUS_S_FAN_SET    0x2F VICTUS_S_FAN_TABLE
0x4C THERMAL_PROFILE        0x52 GRAPHICS_MUX
```

## Прочее

```
Thermal cooling devices: 5× "Fan" (max_state=1), 17× "Processor" (max=3), intel_powerclamp
kernel cmdline: quiet splash, resume=/dev/mapper/root (btrfs, LUKS)
```
