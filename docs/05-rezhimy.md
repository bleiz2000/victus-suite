# 05. Режимы производительности: Windows OMEN vs Linux

## Что делал Shift+F2 в OMEN Gaming Hub (Windows)

`Shift+F2` — хоткей **OMEN Overlay**: оверлей поверх игры с показанием
CPU/GPU температуры, FPS, утилизации и переключателем режима
(**Comfort / Default( Balanced) / Performance**), плюс Fan (Auto/Max/Manual).

Режимы в Windows:

| OMEN | Суть | WMI/EC |
|---|---|---|
| Comfort | холодно и тихо, лимиты вниз | thermal profile `0x02 COOL` |
| Default | сбалансированный | `0x01 DEFAULT` |
| Performance | максимум питания, вентиляторы агрессивнее | `0x00 PERFORMANCE` |
| Fan Max / Manual | форс-режим вентиляторов | `0x27/0x2E` fan queries |

## Что это в Linux

**Да, это то же самое** — но только для *платформенной* части.

```
/sys/firmware/acpi/platform_profile        # low-power | balanced | performance
/sys/firmware/acpi/platform_profile_choices
```

На машине: `hp-wmi` мапит
`PLATFORM_PROFILE_PERFORMANCE → HP_THERMAL_PROFILE_PERFORMANCE (0x00)`,
`BALANCED → DEFAULT (0x01)`, `COOL → COOL (0x02)`, `QUIET → QUIET (0x03)`.

Управление (любое из):

```bash
powerprofilesctl set performance      # ← эквивалент Performance в OMEN
powerprofilesctl set balanced
powerprofilesctl set power-saver      # ← Comfort/Low-power
echo performance | sudo tee /sys/firmware/acpi/platform_profile
```

Сейчас стоит `power-saver` (т.е. «Comfort») — на батарее.

### Чем Linux-параметры питания НЕ равны OMEN Performance

| Слой | Windows OMEN Performance | Linux |
|---|---|---|
| Платформа/BIOS thermal | ✅ | ✅ `platform_profile` |
| Вентиляторы | ✅ Fan Manual/Max | ⚠️ только hwmon PWM (см. docs/04) |
| CPU P-cores turbo / power | ✅ | ⚠️ `intel_pstate`: `max_perf_pct`, `no_turbo`, `energy_performance_preference` (сейчас `power`!) |
| Лимиты CPU package (PL1/PL2) | ✅ | ⚠️ `thermald` + RAPL `/sys/class/powercap/intel-rapl:0/constraint_*_power_limit_uw` |
| GPU power limit / clocks | ✅ | ✅ `nvidia-smi -pl 5..120` |
| GPU temp limit | ✅ | ✅ `nvidia-smi -lgc`, `-plc` |
| iGPU частоты | ✅ | ✅ `/sys/class/drm/card*/gt_min_freq_mhz`, `gt_max_freq_mhz` |
| Оверлей температур/FPS | ✅ Shift+F2 | ❌ надо писать (docs/06) |

**Важно:** `powerprofilesctl set performance` меняет только
`platform_profile` + EPP. Он **не** поднимает PL1/PL2 и **не** меняет
лимит NVIDIA. Поэтому «включил performance, а FPS не вырос» — это ожидаемо.

## FAQ: «Save / Normal / Performance в Windows и режим в моей программе — это одно и то же?»

**Суть одна, слой один, разница — в том, что заодно переключается.**

1. **Один и тот же рычаг.** И в Windows (Управление питанием / OMEN), и в Linux
   режим — это запись в один и тот же **thermal profile BIOS/EC**
   (`HP_THERMAL_PROFILE_PERFORMANCE=0x00`, `DEFAULT=0x01`, `COOL=0x02`,
   `QUIET=0x03`). Windows зовёт его `Comfort/Default/Performance`,
   Linux выдаёт `low-power/balanced/performance`. Это **одна и та же сущность**.
2. **Алгоритмы разные — да.** В Windows это библиотека HP/OMEN (WMI 0x1A +
   собственный менеджер вентиляторов/питания), в Linux это драйвер `hp-wmi`
   + `intel_pstate` + `thermald`. Разные шаги, разная логика, **одна цель**.
3. **Но «полнота» разная.** Переключение режима в Windows OMEN заодно двигает
   PL1/PL2, вентиляторы, GPU power limit, иногда MUX. В Linux
   `powerprofilesctl set performance` двигает **только** платформу + EPP.
   Поэтому «Performance в Linux» ощущается слабее, чем в Windows — это не
   разные режимы, а **разный объём действий под одним именем**.
4. **Вывод для нашей программы:** пресет в `victus profile set performance`
   должен применять **набор** (матрица §4.3.1), тогда по ощущению это будет
   то же самое, что Windows Performance.

Короткая таблица соответствия:

| Windows (питание / OMEN) | Linux (что есть сейчас) | Наш пресет |
|---|---|---|
| Сохранение / Comfort / Eco | `power-saver` / `low-power` | `quiet` |
| Обычная / Balanced / Default | `balanced` | `balanced` |
| Высокая производительность / Performance | `performance` | `performance` |
| Max fans / Turbo | *(нет)* | `max` |

## Что можно крутить вручную (полный список на этой машине)

### CPU (Intel, `intel_pstate=active`)

```bash
# профиль энергии ядер
cat /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference
echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference

# лимиты
cat /sys/devices/system/cpu/intel_pstate/max_perf_pct   # 0..100
echo 100 | sudo tee /sys/devices/system/cpu/intel_pstate/max_perf_pct
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo   #0 = turbo on

# RAPL (PL1/PL2)
cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw  # PL1, µW
echo 45000000 | sudo tee /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
```

### NVIDIA RTX 4060

```bash
nvidia-smi --query-gpu=power.limit,power.min_limit,power.max_limit --format=csv
# 40W / 5W / 120W  (default 80W)
sudo nvidia-smi -pl 100            # поднять лимит до 100W
sudo nvidia-smi -pl 80             # вернуть default
nvidia-smi --query-gpu=temperature.gpu,clocks.gr,utilization.gpu --format=csv
```

### iGPU

```bash
cat /sys/class/drm/card2/gt_max_freq_mhz
echo 1600 | sudo tee /sys/class/drm/card2/gt_min_freq_mhz
```

### Вентиляторы

См. `docs/04-ventilyatory.md`.

## Практическая рекомендация для «режимов»

Daemon должен применять **набор** действий под каждое пресет-имя:

| Пресет | platform_profile | EPP | max_perf_pct | NVIDIA -pl | PWM |
|---|---|---|---|---|---|
| `quiet` | low-power | power | 70 | default | AUTO |
| `balanced` | balanced | balance_performance | 100 | default | AUTO |
| `performance` | performance | performance | 100 | max (120W) | AUTO, порог ниже |
| `max` | performance | performance | 100 | max | 0 (MAX fans) |

Т.е. **одно имя = несколько записей в разные sysfs-файлы**. Именно этого
не хватает, чтобы «Linux-параметры питания» ощущались как OMEN Performance.
