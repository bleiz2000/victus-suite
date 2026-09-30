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
                yield Button(t("tui.tab_kbd"), id="tab-kbd", classes="tab")
                yield Button(t("tui.tab_vertil"), id="tab-vertil", classes="tab")
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
        background: #141c14;
        color: #7ee787;
        text-style: bold;
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
    #presets-panel { width: 22; }
    #color-panel { width: 1fr; }
    #effects-panel { width: 34; }
    #vtelemetry { width: 46; }
    #vcontrol { width: 1fr; }
    #vlimits { width: 32; }

    /* ---- PRESETS ---- */
    .add-row {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0;
        margin: 0 0 1 0;
        border: none;
        background: transparent;
        color: #7ee787;
        text-align: left;
        content-align: left middle;
    }
    .add-row:hover {
        background: #14200f;
        color: #b6ffbc;
    }
    #preset-list {
        width: 100%;
        height: 1fr;
        padding: 0;
        scrollbar-color: #6a6a6a;
        scrollbar-color-hover: #8a8a8a;
        scrollbar-color-active: #a0a0a0;
        scrollbar-background: #141414;
        scrollbar-background-hover: #1c1c1c;
        scrollbar-background-active: #0b0b0b;
    }
    #shell .preset {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0;
        border: none;
        background: #0b0b0b;
        color: #c4c4c4;
        text-align: left;
        content-align: left middle;
    }
    #shell .preset:hover {
        background: #1e1e1e;
        color: #ffffff;
    }
    #shell .preset:focus {
        background: #1e1e1e;
        color: #ffffff;
        text-style: bold;
    }
    #shell .preset.selected {
        background: #e8e8e8;
        color: #000000;
        text-style: bold;
    }
    #mode-block {
        width: 100%;
        height: auto;
        dock: bottom;
        margin-top: 1;
        padding-top: 1;
        border-top: solid #3a3a3a;
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
        background: #1c1c1c;
        color: #ffffff;
    }
    #mode-block Button.mode.on {
        color: #ffffff;
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
        color: #7ee787;
    }

    /* ---- COLOR PICKER ---- */
    #picker-top {
        width: 100%;
        height: 1fr;
        align: left top;
        padding-top: 1;
    }
    .hsv-row {
        width: 100%;
        height: 1;
        align: left middle;
    }
    .hsv-label {
        width: 16;
        height: 1;
        text-align: left;
        color: #c4c4c4;
    }
    .hsv-row AsciiSlider {
        width: 1fr;
        min-width: 6;
        height: 1;
    }
    .hsv-value {
        width: 4;
        height: 1;
        text-align: right;
        color: #9a9a9a;
    }
    #hex-row {
        width: 100%;
        height: 1;
        margin-top: 1;
        align: left middle;
    }
    #hex-input {
        width: 12;
        height: 1;
        padding: 0 1;
        border: none;
        background: #171717;
        color: #e8e8e8;
    }
    #hex-input:focus {
        background: #222222;
        color: #ffffff;
    }
    #picker-bottom {
        width: 100%;
        height: auto;
        margin-top: 1;
        align: left middle;
    }
    #preview {
        width: 14;
        height: 7;
        background: #808080;
        border: none;
        margin-right: 2;
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
        color: #7ee787;
    }
    #picker-actions {
        width: 100%;
        height: 3;
        margin-top: 1;
        align: left middle;
    }
    #picker-actions Button,
    #effect-actions Button,
    #save-actions Button {
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
    #effect-actions Button:hover,
    #save-actions Button:hover {
        background: #2e2e2e;
        color: #ffffff;
    }

    /* ---- EFFECTS ---- */
    #creator {
        width: 100%;
        height: 1fr;
        margin-top: 1;
        padding: 0 1;
        border: solid #4a4a4a;
        border-title-color: #c8c8c8;
        border-title-style: bold;
        border-title-align: center;
        background: #0b0b0b;
    }
    #sine {
        width: 100%;
        height: 100%;
        color: #d0d0d0;
    }
    #speed-row {
        width: 100%;
        height: 1;
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
        height: 1;
    }
    #effect-actions {
        width: 100%;
        height: 3;
        margin-top: 1;
        align: left middle;
    }
    #effect-actions #effect-start {
        background: #10240f;
        color: #7ee787;
    }
    #effect-actions #effect-start:hover {
        background: #17351a;
        color: #b6ffbc;
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
        margin-top: 1;
        padding-top: 1;
        border-top: solid #3a3a3a;
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
        background: #1c1c1c;
        color: #ffffff;
    }
    #v-mode-block Button.mode.on {
        color: #ffffff;
        text-style: bold;
    }
    .vrow {
        width: 100%;
        height: 1;
        margin-top: 1;
        align: left middle;
    }
    .vlabel {
        width: 10;
        height: 1;
        color: #c4c4c4;
    }
    .vrow AsciiSlider {
        width: 1fr;
        min-width: 6;
        height: 1;
    }
    .vvalue {
        width: 14;
        height: 1;
        text-align: right;
        color: #9a9a9a;
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
        color: #8a8a8a;
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
    SavePresetScreen, PickColorScreen {
        align: center middle;
        background: #000000 70%;
    }
    #save-box {
        width: 64;
        height: auto;
        padding: 1 2;
        border: solid #6a6a6a;
        border-title-color: #e8e8e8;
        border-title-style: bold;
        border-title-align: center;
        background: #101010;
    }
    #save-hex {
        width: 100%;
        height: 1;
    }
    #name-input {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    #save-actions {
        width: 100%;
        height: 3;
        margin-top: 1;
        align: left middle;
    }
    #pick-box {
        width: 44;
        height: 16;
        padding: 0 1;
        border: solid #6a6a6a;
        border-title-color: #e8e8e8;
        border-title-style: bold;
        border-title-align: center;
        background: #101010;
    }
    #pick-list {
        width: 100%;
        height: 1fr;
        background: transparent;
        overflow-y: auto;
        scrollbar-color: #6a6a6a;
        scrollbar-color-hover: #8a8a8a;
        scrollbar-background: #141414;
        scrollbar-background-hover: #1c1c1c;
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
        background: #1e1e1e;
        color: #ffffff;
    }
    PickColorScreen .preset:focus {
        background: #1e1e1e;
        color: #ffffff;
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
