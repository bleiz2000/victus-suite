"""Root screen and App of victus_tui — компактный Bento v2.

Компактная сетка под окно ~1/4 экрана 1080p (~110×31 ячеек):
shell (title + вкладки) → body [Подсветка | vertil] → status line.
Вкладки переключаются без размонтирования (display), поэтому эффект
подсветки и автопилот вентиляторов переживают переключение.
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button

from i18n import CONFIG_LOCALE, lang, t
from tui import core
from tui.kbd_tab import KbdTab
from tui.vertil_tab import VertilTab

TABS = (("tab-kbd", "kbd"), ("tab-vertil", "vertil"))


class VictusScreen(Container):
    def compose(self) -> ComposeResult:
        app = self.app
        active = getattr(app, "active_tab", "kbd")
        shell = Vertical(id="shell")
        shell.border_title = t("tui.app_title")
        with shell:
            with Horizontal(id="titlerow"):
                # активная вкладка подсвечена уже на старте (иначе ни одна
                # не выглядит выбранной до первого клика)
                yield Button(t("tui.tab_kbd"), id="tab-kbd",
                             classes=f"tab{' on' if active != 'vertil' else ''}")
                yield Button(t("tui.tab_vertil"), id="tab-vertil",
                             classes=f"tab{' on' if active == 'vertil' else ''}")
                yield Button(t("tui.btn_lang"), id="lang")
            kbd = KbdTab(id="kbd")
            vertil = VertilTab(id="vertil")
            kbd.display = active != "vertil"
            vertil.display = active == "vertil"
            yield kbd
            yield vertil


class VictusApp(App):
    TITLE = "victus-suite"
    CSS_PATH = None
    active_tab = "kbd"
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #cfcfcf;
    }
    #shell {
        width: 100%;
        height: 100%;
        border: solid #4a4a4a;
        border-title-color: #e8e8e8;
        border-title-style: bold;
        background: #0b0b0b;
    }
    #shell #kbd, #shell #vertil {
        width: 100%;
        height: 1fr;
    }
    #titlerow {
        width: 100%;
        height: 1;
        align: left middle;
        margin: 0;
        padding: 0;
    }
    #titlerow .tab {
        width: auto;
        min-width: 0;
        height: 1;
        padding: 0 1;
        margin: 0;
        border: none;
        background: transparent;
        color: #7a7a7a;
        text-align: left;
        content-align: left middle;
    }
    #titlerow .tab:hover {
        background: #1c1c1c;
        color: #e8e8e8;
    }
    #titlerow .tab.on {
        background: #2a2210;
        color: #ffd766;
        text-style: bold;
    }
    #titlerow .tab.on:hover {
        background: #3a2f12;
        color: #fff2c8;
    }
    #titlerow #lang {
        width: auto;
        min-width: 0;
        height: 1;
        padding: 0 1;
        margin: 0;
        border: none;
        background: transparent;
        color: #7ee787;
        text-style: bold;
        text-align: left;
        content-align: left middle;
        dock: right;
    }
    #titlerow #lang:hover {
        background: #14200f;
        color: #b6ffbc;
    }
    #body {
        width: 100%;
        height: 1fr;
    }
    .panel {
        height: 100%;
        margin: 0;
        padding: 0 1;
        border: solid #4a4a4a;
        border-title-color: #e8e8e8;
        border-title-style: bold;
        border-title-align: center;
        background: #0b0b0b;
    }
    /* золотое свечение: рамки и заголовки панелей подсветки */
    #color-panel {
        width: 1fr;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }
    #kside { width: 42; height: 100%; }
    #creator-panel {
        width: 100%;
        height: 1fr;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }
    #effects-panel {
        width: 100%;
        height: auto;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }
    /* ---- VERTIL: компоновка ---- */
    /* всё прижато вверх: управление во всю ширину сверху, ниже ряд
       «телеметрия | безопасность»; пустое — ровной полосой у нижнего
       края панели управления, а не дырой посередине */
    #vcontrol {
        width: 100%;
        height: 1fr;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }
    #vpanels {
        width: 100%;
        height: auto;
    }
    #vtelemetry {
        width: 1fr;
        height: auto;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }
    #vlimits {
        width: 36;
        height: auto;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
    }

    #mode-block {
        width: 100%;
        height: auto;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid #8a6f2a;
    }
    #mode-block Button.mode {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0;
        margin: 0;
        border: none;
        background: transparent;
        color: #b0b0b0;
        text-align: left;
        content-align: left middle;
    }
    #mode-block Button.mode:hover {
        background: #2a2210;
        color: #ffe9a8;
    }
    #mode-block Button.mode.on {
        color: #ffd766;
        text-style: bold;
    }
    .mode-row {
        width: 100%;
        height: 1;
        margin-top: 1;
        align: left middle;
    }
    .mode-label {
        width: auto;
        min-width: 4;
        height: 1;
        padding-right: 1;
        color: #c4c4c4;
    }
    #power {
        width: auto;
        height: 1;
        padding: 0 1;
        border: none;
        background: transparent;
        color: #8a8a8a;
    }
    #power .switch--slider {
        color: #6a6a6a;
        background: #1c1c1c;
    }
    #power.-on .switch--slider {
        color: #ffd766;
    }

    /* ---- COLOR PICKER ---- */
    /* всё прижато вверх: панель тянется, пустое — полосой у нижнего края */
    #picker-top {
        width: 100%;
        height: auto;
        align: left top;
    }
    .slider-row {
        width: 100%;
        height: 2;
        align: left middle;
    }
    /* тонкая линия темноты: одна строка, без подписи и без поля числа */
    .thin-row {
        width: 100%;
        height: 1;
        margin: 0;
        align: left middle;
    }
    .thin-row .slider-label {
        width: 16;
        height: 1;
    }
    .thin-row AsciiSlider {
        width: 1fr;
        min-width: 6;
        height: 1;
        color: #ffffff;
    }
    .slider-label {
        width: 16;
        height: 1;
        text-align: left;
        color: #c4c4c4;
    }
    .slider-row AsciiSlider {
        width: 1fr;
        min-width: 6;
        height: 2;
    }
    #color-panel .slider-row AsciiSlider,
    #effects-panel #speed-row AsciiSlider {
        color: #f0c34f;
    }
    .num-input {
        width: 6;
        height: 1;
        padding: 0 1;
        border: none;
        background: #171717;
        color: #e8e8e8;
    }
    .num-input:focus {
        background: #222222;
        color: #ffffff;
    }
    #color-panel .num-input,
    #effects-panel .num-input {
        background: #171410;
        color: #ffd766;
    }
    #color-panel .num-input:focus,
    #effects-panel .num-input:focus {
        background: #2a2210;
        color: #fff2c8;
    }
    #hex-row {
        width: 100%;
        height: 2;
        margin-bottom: 0;
        align: left middle;
    }
    /* подчёркивание вместо коробки: рамка по всему периметру съедала
       строку контента и поле становилось пустым */
    #hex-input {
        width: 13;
        height: 2;
        padding: 0 1;
        border: none;
        border-bottom: solid #8a6f2a;
        background: #171410;
        color: #ffd766;
    }
    #hex-input:focus {
        border-bottom: solid #ffd766;
        background: #2a2210;
        color: #fff2c8;
    }
    #picker-bottom {
        width: 100%;
        height: auto;
        margin-top: 1;
        align: left middle;
    }
    #preview {
        width: 10;
        height: 5;
        background: #808080;
        border: solid #ffd766;
        margin-right: 1;
    }
    #bottom-right {
        width: 1fr;
        height: auto;
        align: left top;
    }
    #readouts {
        width: 100%;
        height: auto;
    }
    .readout {
        width: 100%;
        height: 1;
        text-align: left;
        color: #b0b0b0;
    }
    .applied {
        color: #ffd766;
    }
    #picker-actions {
        width: 100%;
        height: 3;
        margin-top: 1;
        align: left middle;
    }
    #picker-actions Button,
    #effect-actions Button {
        width: auto;
        min-width: 0;
        height: 3;
        padding: 0 1;
        margin: 0 1 0 0;
        border: none;
        background: #1c1c1c;
        color: #d8d8d8;
        text-style: bold;
        text-align: center;
        content-align: center middle;
    }
    #picker-actions Button:hover,
    #effect-actions Button:hover {
        background: #2e2e2e;
        color: #ffffff;
    }
    #picker-actions #apply {
        background: #ffd766;
        color: #0b0b0b;
    }
    #picker-actions #apply:hover {
        background: #ffe9a8;
        color: #0b0b0b;
    }
    #picker-actions #copy-hex {
        background: #241d0c;
        color: #ffd766;
    }
    #picker-actions #copy-hex:hover {
        background: #3a2f12;
        color: #fff2c8;
    }

    /* ---- EFFECTS ---- */
    #creator-panel #sine {
        width: 100%;
        height: 100%;
        color: #f0c34f;
    }
    #speed-row {
        width: 100%;
        height: 2;
        margin-top: 1;
        align: left middle;
    }
    #speed-label {
        width: auto;
        height: 1;
        padding-right: 1;
        color: #c4c4c4;
    }
    #speed-row AsciiSlider {
        width: 1fr;
        min-width: 6;
        height: 2;
    }
    #effect-actions {
        width: 100%;
        height: 3;
        margin-top: 1;
        align: left middle;
    }
    #effect-actions #effect-start {
        background: #ffd766;
        color: #0b0b0b;
    }
    #effect-actions #effect-start:hover {
        background: #ffe9a8;
        color: #0b0b0b;
    }
    #effect-actions #effect-stop {
        background: #2a1010;
        color: #ff7b7b;
    }
    #effect-actions #effect-stop:hover {
        background: #3d1616;
        color: #ffb3b3;
    }

    /* ---- VERTIL ---- */
    #vbody {
        width: 100%;
        height: 1fr;
    }
    .vblock {
        width: 100%;
        height: auto;
        margin-top: 1;
        text-align: left;
        color: #b0b0b0;
    }
    #v-temps, #v-limits {
        margin-top: 0;
    }
    #v-mode-block {
        width: 100%;
        height: auto;
        margin-bottom: 0;
        padding-bottom: 1;
        border-bottom: solid #8a6f2a;
    }
    #v-mode-block Button.mode {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0;
        margin: 0;
        border: none;
        background: transparent;
        color: #b0b0b0;
        text-align: left;
        content-align: left middle;
    }
    #v-mode-block Button.mode:hover {
        background: #2a2210;
        color: #ffe9a8;
    }
    #v-mode-block Button.mode.on {
        color: #ffd766;
        text-style: bold;
    }
    #v-knobs {
        width: 100%;
        height: auto;
        align: left top;
    }
    #v-readouts {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    #v-readouts .vblock {
        margin-top: 0;
        height: auto;
    }
    /* золотое свечение вентиляторов — тот же росчерк, что на «Подсветке» */
    #vcontrol .slider-row AsciiSlider {
        color: #f0c34f;
    }
    #vcontrol .num-input {
        background: #171410;
        color: #ffd766;
    }
    #vcontrol .num-input:focus {
        background: #2a2210;
        color: #fff2c8;
    }

    /* ---- status ---- */
    #statusline {
        width: 100%;
        height: 1;
        align: center middle;
    }
    #status-flow {
        width: 100%;
        height: 1;
        align: center middle;
    }
    #color-tag {
        width: auto;
        height: 1;
        padding-right: 2;
        color: #ffd766;
    }
    #status {
        width: auto;
        height: 1;
        color: #7ee787;
    }
    #vstatusline {
        width: 100%;
        height: 1;
        align: center middle;
    }
    #vstatus-flow {
        width: 100%;
        height: 1;
        align: center middle;
    }
    #vstatus-tag {
        width: auto;
        height: 1;
        padding-right: 2;
        color: #8a8a8a;
    }
    #vstatus {
        width: auto;
        height: 1;
        color: #7ee787;
    }

    /* ---- modals ---- */
    PickColorScreen {
        align: center middle;
        background: #000000 70%;
    }
    #pick-box {
        width: 44;
        height: 16;
        padding: 0 1;
        border: solid #8a6f2a;
        border-title-color: #ffd766;
        border-title-style: bold;
        border-title-align: center;
        background: #101010;
    }
    #pick-list {
        width: 100%;
        height: 1fr;
        background: transparent;
        overflow-y: auto;
        scrollbar-color: #8a6f2a;
        scrollbar-color-hover: #ffd766;
        scrollbar-background: #141210;
        scrollbar-background-hover: #171410;
    }
    PickColorScreen .preset {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0;
        border: none;
        background: transparent;
        color: #c4c4c4;
        text-align: left;
        content-align: left middle;
    }
    PickColorScreen .preset:hover {
        background: #2a2210;
        color: #fff2c8;
    }
    PickColorScreen .preset:focus {
        background: #2a2210;
        color: #ffd766;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("q", "quit", "Выход"),
        ("ctrl+c", "quit", None),
        ("ctrl+r", "refresh", "Обновить"),
    ]

    def compose(self) -> ComposeResult:
        yield VictusScreen()

    def on_mount(self):
        # «фоновый демон + TUI» (docstring victus_tui): если victusd ещё нет —
        # поднимаем, чтобы эффекты были онлайн и в фоне, как у трей
        self.run_worker(core.ensure_daemon(), exclusive=True, group="daemon")

    def action_refresh(self):
        if self.active_tab == "vertil":
            # _boot сам показывает статус доступа (нужен пароль / готово)
            self.query_one("#vertil")._boot()
            return
        tab = self.query_one("#kbd")
        tab._sync_controls()
        tab._set_status(t("tui.status_ready"))

    def _show_tab(self, name: str):
        """Переключение вкладок без размонтирования: display, не remove."""
        if name not in ("kbd", "vertil"):
            return
        self.active_tab = name
        for bid, tab_id in TABS:
            tab = self.query_one("#%s" % tab_id)
            tab.display = name == tab_id
            self.query_one("#%s" % bid, Button).set_class(name == tab_id, "on")
        shown = self.query_one("#%s" % name)
        first = shown.query("Button").first()
        if first is not None:
            first.focus()

    async def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "lang":
            event.stop()
            await self.toggle_language()
        elif bid in dict(TABS):
            event.stop()
            self._show_tab(dict(TABS)[bid])

    async def toggle_language(self):
        """Переключить язык и пересобрать интерфейс.

        Подписи считаются один раз при сборке (t() в compose), поэтому
        одного refresh мало — дерево создаётся заново, а состояние
        (цвет, стопы, скорость, вкладка, автопилот) поднимается из state-файла.
        """
        new = "en" if lang().startswith("ru") else "ru"
        try:
            with open(CONFIG_LOCALE, "w", encoding="utf-8") as f:
                f.write(new + "\n")
        except OSError:
            return
        kbd = self.query_one("#kbd")
        vertil = self.query_one("#vertil")
        was_running = bool(kbd.running)
        was_auto = bool(vertil.autopilot)
        KbdTab._rebuilding = True
        VertilTab._rebuilding = True
        try:
            screen = self.screen
            await screen.remove_children()
            await screen.mount(VictusScreen())
        finally:
            KbdTab._rebuilding = False
            VertilTab._rebuilding = False
        if was_running:
            self.query_one("#kbd").restore_running()
        if was_auto:
            self.query_one("#vertil").autopilot = True
        self._show_tab(self.active_tab)
