# Отчёт: интеграция вкладки «vertil» в TUI (сессия 2026-09-30)

**Дата:** 2026-09-30, 20:00–22:00 (+04) · **Машина:** HP Victus 16-r0xxx,
board 8BBE, BIOS F.26, ядро `7.2.5-3-omarchy`, Textual 8.2.8
**Область:** вторая вкладка TUI «Вентиляторы» + мост записи без пароля.
Код подсветки (`kbd_tab.py`, движок `core.py`, палитра) не менялся.
**Итог сессии:** консольный пульт готов, TUI-интеграция завершена и
проверена headless-смоуком, релиз `v1.1.0-beta` опубликован.
**Осталось:** финальное тестирование записи на живом железе из вкладки.

---

## 1. Что сделано

| Файл | Роль |
|---|---|
| `bin/tui/vertil_tab.py` (новый) | вкладка: ТЕЛЕМЕТРИЯ / УПРАВЛЕНИЕ / БЕЗОПАСНОСТЬ + статус-строка с чипом |
| `bin/tui/vertil_core.py` (новый) | мост: снимок телеметрии, запись `fanctl`, probe прав, hold на выходе |
| `bin/tui/screens.py` | CSS вкладки и панелей, `_show_tab()`, refresh для vertil, `toggle_language` |
| `bin/victus-kbd` | подкоманда `fans <cmd>` → `vertil/tools/fanctl.py` (NOPASSWD-цель) |
| `locales/ru.json`, `locales/en.json` | ~43 ключа `tui.*` + `kbd.fans_missing`, расширен `kbd.usage` |
| `vertil/tools/fanctl.py`, `fanlib.py` | консольный пульт (готов ранее в этой же сессии) |

Композиция вкладки:

- **ТЕЛЕМЕТРИЯ** — CPU/GPU/VRM* (ACPI-прокси `TCPU_PCI`), обороты правого и
  левого вентилятора, duty PWM, режим hwmon, RAPL/nvidia-ватты; пустые
  колонки не рисуются.
- **УПРАВЛЕНИЕ** — кнопки `[ ] Manual / [ ] SMART / [ ] BIOS Auto` и два
  слайдера PWM 0..255 с оценкой `~RPM`; подписи слайдеров **всегда
  по-английски** (`Right fan` = CPU = `pwm1`, `Left fan` = GPU = `pwm2`),
  телеметрия — на языке интерфейса (`правый`/`левый`).
- **БЕЗОПАСНОСТЬ** — `guard`/`smart`/`emerg`/`hold`/`preset` из
  `vertil/config/presets.json` + вердикт доступа (`passwordless`).
- **Статус-строка** — чип состояния: `SMART ▸ 128/140`, `PWM 57/57`,
  авария `!! 93/83 °C`.

Режимы: Manual (слайдеры, запись через 0.4 с после отпускания), SMART
(`fanlib.Smart`, шаг 1 с, `FAIL_STOP=10`), BIOS Auto (**двойное
подтверждение за 30 с** — переход глушит лопасти на ~215 с).

## 2. Запись без пароля

```
VertilTab ─► vertil_core.call("set-pwm"|"set-mode"|"hold")
             └─► sudo -n bin/victus-kbd fans <cmd>   ← NOPASSWD-правило README
                 └─► vertil/tools/fanctl.py ─► fanlib ─► /sys/.../hwmon*
```

- `_wrapper()` строит `["sudo","-n",KBD,"fans",…]`, фоллбэк
  `["sudo","-n",python,fanctl,…]`; без root права не нужны — идём напрямую.
- `probe_access()` зовёт не `sudo true`, а реальную запись
  (`… victus-kbd fans status`) → вердикт `direct | sudo | need-password |
  no-hwmon | error`.
- Новое sudoers-правило **не добавлялось** (пункт правил §0 — не форсить
  NOPASSWD без согласования): используется уже выданное правило на
  `victus-kbd`.
- Проверено на этой машине: `sudo -n …/bin/victus-kbd fans status` и
  `set-pwm 79 92` → `rc=0`, пароль не запрашивается.

## 3. Локализация ru/en

- Все новые строки — ключи `tui.*` в **оба** файла локалей; на момент
  сдачи: по **149** ключей в `ru.json` и `en.json`, расхождений нет
  (проверка `set(keys_ru) == set(keys_en)`).
- `kbd.fans_missing` — сообщение о недоступном backend; `kbd.usage`
  дополнен строкой `fans status | set-pwm A B | set-mode 0|1|2 | hold N`.
- `config/locale` в конце сессии = `ru` (дефолт; тест возвращает его через
  `atexit`).
- Смена языка пересоблывает обе вкладки, поэтому:
  - `VertilTab._rebuilding` / `KbdTab._rebuilding` запрещают размонтирование
    во время пересборки — иначе `on_unmount` глушит автопилот;
  - `session{controlled, autopilot}` живёт в `vertil_core` и переживает
    пересборку;
  - активная вкладка и состояние автопилота восстанавливаются.

## 4. Исправления по ходу (что сломалось и почему)

| Симптом | Причина | Исправление |
|---|---|---|
| Первый запуск: `TypeError` при старте вкладки | `@work`-декорированный метод нельзя передавать в `run_worker(...)` — обёртка не принимает аргументы | `_boot()`/`_tick()` зовутся напрямую (декоратор сам стартует воркер) |
| `AttributeError: _render` | имя метода `VertilTab._render` конфликтовало с `Widget._render` | переименован в `_paint(snap)` |
| кнопка режима не подсвечивалась | `_mode` не был известен до первой записи | первый снапшот читает `mode_name` из железа |
| «уже ручной режим» → ложная ошибка про пароль | `_to_manual` писала `set-mode 1` даже когда `mode_name == "manual"` | ранний выход без записи |
| перенос строк в панели БЕЗОПАСНОСТЬ | длинные значения (`CPU 99.0 · GPU 88.0 °C`) | `fmt_c()`: `CPU 99 · GPU 88 °C` |
| пустая колонка CPU-ватт | RAPL есть не везде | колонка рисуется только при `cpu_w is not None` |
| `ok, msg = a if ok else b` — путаница | тернарник на кортежах | нормальный `if/else` |
| обе вкладки «мертвы» после переключения | unmount глушил таймер/автопилот | вкладки всегда смонтированы, переключение через `display` |
| статус показывал дрожащий readback | hp-wmi не отдаёт setpoint (report §7) | показываем последнюю команду `self._setpoint` |
| слайдеры писали на каждый пиксель | событие на каждый tick | debounce `set_timer(0.4)` |

## 5. Headless-тесты

Смоук: `/tmp/opencode/vertil_smoke.py` (вне репозитория — нужен Textual
`App.run_test`; восстанавливает `config/locale` через `atexit`).

Что проверяет: монтирование обеих вкладок, первый снимок и статус доступа,
переключение клавиатура ↔ vertil, **смену языка с сохранением активной
вкладки и автопилота**, панель лимитов (EN), статус и чип состояния,
возврат локали `ru`.

Результат последнего прогона (21:47):

```
back to kbd: active=kbd kbd=True vert=False
after lang: active=vertil kbd=False vert=True
--- limits(en) ---
guard   CPU 99 · GPU 88 °C
smart   60..255
emerg   CPU 93 · GPU 83 °C
hold    180 PWM
preset  victus-2026-09-30
access  passwordless
--- status(en): fans connected — control enabled
--- tag(en): PWM 57/57
locale back to: ru
SMOKE OK
```

Дополнительно: `ast.parse` по всем правленым `.py`, JSON-валидность обеих
локалей, скриншоты `vertil_tab.png` / `vertil_en.png` (визуальная проверка
выравнивания колонок, отсутствия переносов и подписей `Right fan`/`Left fan`).

**Ограничение:** смоук пишет только в память/файлы — он не подменяет
проверку записи на живом hwmon (см. §7).

## 6. Релиз

- Коммит `35cc07a feat(vertil): вкладка «Вентиляторы» …` + `2acf5bf` (журнал),
  запушены в `main`.
- Тег `v1.1.0-beta` → GitHub Release (prerelease),
  артефакт `victus-suite.tar.gz` (193 134 байта, 100 файлов) собран
  `git archive --format=tar.gz --prefix=victus-suite/`.
- Notes релиза: EN основной, RU второстепенный; README (обе версии) получил
  раздел «Fans — telemetry and control (vertil tab)» с архитектурой.

## 7. Статус и что осталось

| Этап | Статус |
|---|---|
| Консольный пульт (`fanctl`, `fanpult`, `victus-kbd fans`, lab-стенд) | ✅ готов |
| Данные железа и пороги (`presets.json`, отчёты §1–§5) | ✅ замерено |
| TUI-интеграция вкладки | ✅ завершена |
| Headless-смоук + статические проверки | ✅ SMOKE OK / AST / JSON |
| Документация и релиз | ✅ `v1.1.0-beta` |
| **Финальное тестирование записи на живом железе** | ⬜ **осталось** |

Чек-лист финального теста (из вкладки, без sudo-пароля):

1. `set-pwm` в ручном режиме → `pwm1`/`pwm2` в sysfs меняются, RPM реагирует,
   чип статуса показывает `PWM p1/p2`.
2. `set-mode 1` → `pwm1_enable == 1`; возврат в BIOS Auto (двойной клик) →
   `pwm1_enable == 2`, rpm падает/поднимается, статус зелёный.
3. SMART 1–2 минуты под нагрузкой → пары `pwm1/pwm2` меняются, статус
   `SMART ▸ …`.
4. Закрытие окна в ручном режиме → в sysfs выставлен `hold 180`.
5. Отключение правила NOPASSWD (переименовать `/etc/sudoers.d/victus-suite`)
   → вердикт `need password`, автопилот останавливается после 10 ошибок, а
   не молчит.

Также отложено: нумерация `Fan 1`/`Fan 2` в телеметрии (сейчас
`правый`/`левый`), вкладка «Питание», CLI температур.

## 8. Очистка артефактов

- Из корня репозитория удалены скриншоты `victus-suite_*.svg` (артефакты
  `save_screenshot`, их и так глотает `.gitignore`).
- В `/tmp/opencode/` убраны временные картинки и архив релиза; оставлены
  `vertil_smoke.py` (смоук, на него ссылается `PROGRESS_LOG.md`) и
  `release_notes_v1.1.0-beta.md` (исходник опубликованных notes).
- В git не попали: бинарники стенда (`lab/cpuburn`, `lab/gpuload`), его
  runtime (`*.log`, `*.state`), `__pycache__`, `logs/`, `state/`,
  `vertil/docs/logs/`.
- `git status` чистый: рабочее дерево без немониторенных изменений.

## 9. Воспроизводимость

```bash
python3 /tmp/opencode/vertil_smoke.py      # headless-смоук (locale вернётся в ru)
sudo -n bin/victus-kbd fans status          # probe прав без пароля
victus_tui                                  # живой прогон вкладки
tail -f logs/victus.log                     # что реально писалось
```
