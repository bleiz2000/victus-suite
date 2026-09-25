# 04. Вентиляторы и тепло

## Что уже есть без единой правки ядра

На этой машине ядро `7.2.5-3-omarchy` содержит upstream `hp-wmi` с hwmon:

```bash
# состояние
cat /sys/class/hwmon/hwmon7/name              # hp
cat /sys/class/hwmon/hwmon7/fan1_input        # CPU RPM (2200)
cat /sys/class/hwmon/hwmon7/fan2_input        # GPU RPM (2500)
cat /sys/class/hwmon/hwmon7/pwm1_enable       # 2 = AUTO
cat /sys/class/hwmon/hwmon7/pwm1 pwm2         # 96 / 109

# включить ручной режим
echo 1 > /sys/class/hwmon/hwmon7/pwm1_enable   # 1 = MANUAL, 0 = MAX, 2 = AUTO
echo 180 > /sys/class/hwmon/hwmon7/pwm1        # 0..255 → RPM по таблице
echo 2 > /sys/class/hwmon/hwmon7/pwm1_enable   # вернуть AUTO
```

`pwm1_enable` общий для `pwm1` и `pwm2` (в драйвере `pwm2` не имеет своего
enable) — **нельзя** крутить CPU и GPU отдельно через enable, но можно задавать
разные значения `pwm1`/`pwm2`.

### Семантика (из hp-wmi.c)

```c
PWM_MODE_MAX    = 0,
PWM_MODE_MANUAL = 1,
PWM_MODE_AUTO   = 2,
#define HP_FAN_SPEED_AUTOMATIC 0x00
```

Запись в `pwm1` возможна **только** при `pwm1_enable == 1`, иначе `-EINVAL`.
Значение 0 при MANUAL трактуется как `HP_FAN_SPEED_AUTOMATIC` → возврат в AUTO.

### Тайминг (критично!)

- В BIOS есть требование **10-секундный stagger** между вентиляторами
  (второй вентилятор ставим на ~+10 с).
- Драйвер держит режим **120 с** (`hp_wmi_get_fan_count_userdefine_trigger` +
  `keep_alive_dwork`) — после таймаута ноутбук уходит в fallback (AUTO).
- Практика из `victus-control`: watchdog переприменяет кривую **каждые 90 с**.

→ Daemon обязан: цикл 2–5 с по температурам, ре-примен кривой каждые 90 с,
второй вентилятор с задержкой 10 с.

### Текущая кривая по умолчанию

`fan1=2200 / fan2=2500 RPM` в AUTO на простое. Это и есть «проблема»,
ради которой делают ручное управление (в Windows OMEN тот же эффект).

## Датчики для кривой

| Метка | Путь |
|---|---|
| CPU Package | `/sys/class/hwmon/hwmon8/temp1_input` (coretemp, `Package id 0`) |
| Ядра | `temp2..temp25` + `temp*_label` |
| ACPI зона | `/sys/class/hwmon/hwmon1/temp1_input` (acpitz) |
| NVMe | `/sys/class/hwmon/hwmon3/temp1..3_input` |
| GPU | `nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader` |
| RPM | `/sys/class/hwmon/hwmon7/fan1_input`, `fan2_input` |

Значения в миллиградусах → `/1000`.

## Термальные подсистемы, которые уже работают

- `thermald` (active) — ACPI/Intel thermal daemon, сам режет при97 °C.
- `intel_powerclamp`, `Processor` cooling devices (max_state=3).
- `power-profiles-daemon` → `platform_profile`.

Их **не надо вытеснять** — наш daemon должен работать *рядом*:
задавать PWM, но откатываться в AUTO при перегреве (fail-safe).

## Резервные пути (если hwmon отсутствует — старые ядра/другие модели)

1. **WMI query 0x2E** (`HPWMI_VICTUS_S_FAN_SPEED_SET`) — требует своего
   модуля/реализации `hp_wmi_perform_query` (в user-space не отдаётся).
2. **DKMS-модуль** на основе патча `hp-wmi` (так делают `hp-wmi-extended`,
   `omen-fan-control`) — но это уже «не для всех дистрибутивов» из коробки.
3. **EC-запись** — как с RGB, но смещения фанов неизвестны и **опасны**:
   в EC по горячим следам лежат тайминги, стоп-байты, счётчики.
   Делать только после реверса и только на своей ревизии.

## Риски

- Запись PWM = ручное управление охлаждением. Ошибка кривой → троттлинг/перегрев.
- Обязательный fail-safe: при `temp > порога` (напр. CPU 92 °C / GPU 83 °C)
  → немедленно `pwm1_enable=2` (AUTO) и лог.
- Нельзя писать PWM во время сна/пробуждения (race с firmware).
- `pwm` недоступен, если `hp_wmi_fan_control_supported()` false
  (проверяется по DMI) — тогда только AUTO/MAX.
