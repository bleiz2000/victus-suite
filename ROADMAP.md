# ROADMAP.md — из скрипта в самостоятельное приложение

**Текущая версия:** `1.2.0` (см. `VERSION`) · **Цель этого документа:** `v1.0.0` stable.

> **EN TL;DR:** the project works as a folder of scripts (`./install.sh` makes
> symlinks). To become a real app it needs packaging (a Python package with
> console entry points), a proper installer (desktop entry, autostart, user
> service), a background daemon + tray instead of "open a terminal", and a
> distribution channel (GitHub Releases + AUR). Steps R1…R5 below are ordered so
> that each one is independently shippable and reversible.

---

## Где мы сейчас (входная точка)

| | |
|---|---|
| Код | `bin/` — набор исполняемых файлов, импортирующих друг друга через `sys.path.insert` |
| Установка | `./install.sh` кладёт симлинки в `~/.local/bin` |
| Меню приложений | ✅ есть: `./install.sh` → `victus-suite.desktop` (`Victus Suite`) + ч/б иконка в `hicolor` |
| Права | ручной sudoers (`/etc/sudoers.d/victus-suite`) или запрос пароля |
| Фон | `victusd` (unix-сокет) + `victus-tray` (AyatanaAppIndicator3): TUI сам поднимает демон при открытии (`ensure_daemon`), трей — по желанию |
| UI | `victus_tui` — Textual, окно 960×540 (`--window`) или терминал |
| Дистрибуция | `git clone` либо артефакт GitHub Release `v1.2.0` (`victus-suite.tar.gz`) |
| Тесты | `pytest vertil/tools/lab/test_fanlib.py` → **20** (в репозитории) + смоук-сьюты в `/tmp/opencode/` (не в репозитории) |

Что это значит: приложение **работает**, но **не устанавливается само**, не
автозапускается и не обновляется. Этапы ниже закрывают именно эту дыру,
не трогая логику подсветки.

---

## R1. Упаковка кода в Python-пакет (1–2 дня)

Сейчас `bin/victus_tui`, `bin/victusd`, `bin/victus-tray` — скрипты с
`sys.path.insert(os.path.dirname(__file__))`. Пакет должен жить в `src/`.

- [ ] Создать `pyproject.toml` (setuptools или hatchling):
      `name = "victus-suite"`, `version` читается из `VERSION`.
- [ ] Перенести код: `bin/` → `src/victus_suite/`
      (`kdb.py` ← `victus-kbd`, `cli_changer.py`, `palette.py`, `log.py`,
      `i18n.py`, `daemon.py` ← `victusd`, `tray.py`, `tui/{core,screens,kbd_tab,slider}.py`).
- [ ] `[project.scripts]` — точки входа без симлинков:
      `victus = victus_suite.cli:main`, `victusd = ...`, `victus-tray = ...`,
      `Changer = ...`, `ColorMaker = ...`, `victus-report = ...`.
- [ ] Ресурсы пакета: `locales/*.json`, `config/colors.conf` → `importlib.resources`
      (чтобы работало из wheel, а не только из папки проекта).
- [ ] Данные пользователя → XDG: `state/` → `${XDG_STATE_HOME:-~/.local/state}/victus-suite/`,
      `logs/` → `${XDG_STATE_HOME}/victus-suite/logs/`, `config/` → `${XDG_CONFIG_HOME}/victus-suite/`.
      Переходный режим: если старая папка рядом со скриптом есть — читать её (compat).
- [ ] `install.sh` переписать на `pip install --user .` / `pipx install .` (симлинки больше не нужны).

**Критерий приёмки:** `pip install .` в чистый venv → `victus --help`,
`victusd --verbose`, `victus_tui --window` работают из любой директории;
старые симлинки `./install.sh --remove` корректно удаляются.

**Риск:** `victus-kbd` вызывается по абсолютному пути из sudoers-правила —
после переезда правило надо перегенерировать (см. R2).

---

## R2. Нормальный установщик (1 день)

- [x] **Меню приложений — ✅ сделано (v1.0.0-beta):** `./install.sh` генерирует
      `~/.local/share/applications/victus-suite.desktop`
      (`Name=Victus Suite`, `Exec=<root>/bin/victus_tui --window`,
      `Terminal=false`, `Categories=Settings;HardwareSettings;`),
      копирует иконки в `~/.local/share/icons/hicolor/`, обновляет кэши
      (`update-desktop-database`, `gtk-update-icon-cache`), `--remove` всё чистит.
- [x] **Иконка — ✅ сделана (v1.0.0-beta):** чёрно-белая минималистичная «V»
      на чёрной плитке; исходник `share/icons/victus-suite.svg`, PNG 16…512 в
      `share/icons/hicolor/`, генератор `share/icons/make_icon.py` (PIL,
      supersampling 4×), есть и scalable SVG.
- [ ] `install.sh` → `make install`: реальная проверка зависимостей перед
      установкой (сейчас ставит «вслепую»).
- [ ] Автогенерация sudoers-правила (с проверкой `visudo -c` и откатом при ошибке).
- [ ] Полноценный `uninstall`: пакет + `.desktop` + автозапуск + sudoers
      (сейчас `--remove` убирает симлинки, ярлык и иконки — sudoers вручную).
- [ ] Проверка окружения: Arch/Debian/Fedora, наличие `python≥3.11`,
      `textual`, `ayatana-appindicator3`, Wayland/X11, гиперсессор
      (Hyprland/Sway/GNOME/KDE) — с понятным сообщением, чего не хватает.

**Критерий приёмки:** на чистой машине `git clone … && ./install.sh` →
в меню приложений есть **Victus Suite** с ч/б иконкой и она открывается
(`gtk-launch victus-suite`), `victus_tui --window` открывается, трей-иконка
есть, повторный запуск установщика идемпотентен,
`./install.sh --remove` не оставляет мусора.

---

## R3. Фоновый сервис вместо «открой терминал» (2–3 дня)

Сейчас демон стартует из TUI и живёт, пока жив процесс. Цель: приложение
запускается при входе в систему и работает всегда.

- [ ] `systemd --user` unit `victus-suite.service`
      (`ExecStart=victusd`, `Restart=on-failure`, `WantedBy=default.target`,
      `After=graphical-session.target`).
- [ ] `systemd --user` unit `victus-suite-tray.service` — иконка в трее
      автоматически (с проверкой, что `ayatana-appindicator3` доступен,
      иначе unit не стартует, а не падает с ошибкой).
- [ ] `victus_tui --window` подключается к уже работающему демону, а не
      порождает второй (уже так, оставить и покрыть тестом).
- [ ] Автозапуск для не-systemd (Hyprland `exec-once`, Sway `exec`, OpenRC) —
      через `victus --autostart install|remove`.
- [ ] Восстановление состояния при выходе из сна (хук `PrepareForSleep`
      или `post`-скрипт suspend/resume) — свет возвращается после пробуждения.
- [ ] `victus-tray` без окна: уведомление при аварии записи в EC (банк-нота
      вместо исключения в stderr).

**Критерий приёмки:** перезагрузка → подсветка восстановлена, иконка в трее
на месте, `systemctl --user status victus-suite` active, TUI открывается
мгновенно и показывает текущий цвет.

---

## R4. Дистрибуция (2–3 дня)

- [ ] **GitHub Releases**: тег `v1.0.0`, артефакт `victus-suite-<ver>.tar.gz`
      (src + wheel + `.desktop` + иконка), `RELEASE_NOTES.md`.
- [ ] GitHub Actions `.github/workflows/ci.yml`:
      lint (`ruff`) → `pytest`/смоук-сьюты → сборка wheel → проверка
      `pip install dist/*.whl && victus --help` → создание релиза по тегу.
- [ ] **AUR**: `PKGBUILD` («victus-suite» + `victus-suite-git`), установка
      `yay -S victus-suite`; после R1 пакет ставится как обычный pip-пакет.
- [ ] Опционально: `.deb`/`.rpm` (или `fpm`/`nuitka`-сборка), AppImage для
      «скачал и открыл» без Python в системе.
- [ ] README: бейджи версии/лицензии, скриншот/гифка окна, блок
      «Install» с одной командой для каждой ОС.
- [ ] `CHANGELOG.md` по [Keep a Changelog](https://keepachangelog.com/) —
      вести от v1.0.0.

**Критерий приёмки:** релиз можно поставить одной командой, CI зелёный на
main, AUR собирается на чистом chroot.

---

## R5. Качество и доверие (1 день, параллельно)

- [ ] Перенести 6 смоук-сьютов из `/tmp/opencode/v2/` в `tests/`
      (`pytest` + `textual`-headless), чтобы они жили в репозитории.
- [ ] `ruff check` + `ruff format --check`, `pyright`/`mypy` на `src/`.
- [ ] `make check` = lint + typecheck + tests (186 проверок должны остаться зелёными).
- [ ] Задокументировать ручную проверку железа: `sudo -n victus-kbd get`,
      цикл с `--delay 1.25` / `--delay 0.05` (см. README → Install).
- [ ] Прогон на второй машине/дистрибутиве — чек-лист.

**Критерий приёмки:** `make check` проходит локально и в CI; тесты не трогают
живой EC без `VICTUS_DRY_RUN=1`.

---

## Порядок и зависимости

```
R1 (пакет) ──► R2 (установщик) ──► R4 (дистрибуция)
     │                │
     └──────────────► R3 (сервис) ──► R4 (AUR/релиз)
                        R5 (качество) — с первого дня, параллельно
```

R1 — фундамент: без него R2–R4 переделываются дважды.
R3 можно делать и до R1 (unit-файл вызывает существующие скрипты), но после
R1 путь к бинарям станет стабильным — меньше переделок.

## Что НЕ входит в этот этап

Это дорожная карта по **упаковке и дистрибуции**. Функциональные ветки
(вентиляторы, температуры, профили питания, оверлей, Material Design)
остаются в `START_DEVELOPMENT.md` §4 и `TZ.md` §8 — их не подмешивать
в R1…R5, чтобы релиз 1.0 был предсказуемым.

---

## Контрольные точки версий

| Версия | Что значит | Статус |
|---|---|---|
| `v1.0.0-beta` | Bento-TUI 960×540, спокойный режим, динамическая амплитуда, умная проверка прав, демон + трей | ✅ зафиксировано этим коммитом |
| `v1.1.0-beta` | вкладка TUI «Вентиляторы» (`vertil`): телеметрия, Manual/SMART/AUTO, запись без пароля через `victus-kbd fans` | ✅ зафиксировано этим коммитом |
| `v1.1.1` | автозапуск SMART при открытии TUI + память выбранного режима (`state/fan_mode.json`), плавные цветовые циклы, поднят демон из TUI, язык по умолчанию en, чистка мёртвых ключей локалей | ✅ зафиксировано этим коммитом |
| `v1.1.2` | линия яркости 0..100 % с живой записью (вместо чёрный↔белый), плотная компоновка обеих вкладок + золото, версионный хендшейк демона (конец битвы за EC), авария SMART без мгновенного прыжка в 100 %, потолок темпа мыши | ✅ зафиксировано этим коммитом |
| `v1.2.0` | аудит 02.10: вкладка «Питание» с режимом «Печатная машинка» (root-хелпер `victus-power`, NOPASSWD, обратимый откат), ползунок потолка **5–25 Вт на всю систему** (PL1/PL2, `max_perf_pct`, потолок частоты, дискретка в авто), остаток заряда с Вт и ETA против цели 5 ч, подсказка с реальным расходом; **подсветка с клавиатуры корпуса** (`victus-kbd power`) с синхронизацией тумблера в TUI; одноканальный PWM hp-wmi + усиленный VRM-фильтр; **дополнено 03.10 (вечер)**: **один ползунок 5–25 Вт на всю систему** (второй ползунок удалён): яркость/частоты/BT/Wi-Fi/USB/фон по ярусам, принудительные 60 Гц, **замер факта 30 с от батареи после применения** с ужатием CPU и честным вердиктом «взята / не взята, пол X Вт», живая строка «цель / факт / CPU / плата», `cascade|cascade-off|brightness|measure`, аудит энергии с отчётом `vertil/docs/2026-10-03-power-floor-report.md` (пол ~9.6 Вт → 5.5 ч), SEO релизов (скриншоты, EN+RU, description + topics репо) | ✅ зафиксировано этим коммитом |
| `v1.0.0-rc.1` | R1 + R2: пакет, установщик, `.desktop`, автозапуск | ⬜ |
| `v1.0.0-rc.2` | R3 + R5: systemd --user, трей из коробки, CI | ⬜ |
| `v1.0.0` | R4: GitHub Release + AUR, CHANGELOG | ⬜ |
| `v1.1.0` | температуры / профили питания (вентиляторы — в `v1.1.0-beta`) | ⬜ |
