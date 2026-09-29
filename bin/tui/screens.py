"""Root screen and App of victus_tui — v1.2 layout per approved mockup.

Three panels on a dense 16:9 grid, thin monochrome borders, no dead space:
shell (title) → body [PRESETS | COLOR PICKER | LIGHTING EFFECTS] → status line.
Only «Подсветка» exists now — fans/power tabs are later stages.
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical

from i18n import t
from tui.kbd_tab import KbdTab


class VictusScreen(Container):
    def compose(self) -> ComposeResult:
        shell = Vertical(id="shell")
        shell.border_title = t("tui.app_title")
        with shell:
            yield KbdTab(id="kbd")


class VictusApp(App):
    TITLE = "victus-suite"
    CSS_PATH = None
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
    #shell #kbd {
        width: 100%;
        height: 100%;
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
    #presets-panel { width: 20; }
    #color-panel { width: 1fr; }
    #effects-panel { width: 36; }

    #preset-list {
        width: 100%;
        height: 100%;
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

    #picker-top {
        width: 100%;
        height: 1fr;
        align: left top;
    }
    #hsv-column {
        width: 1fr;
        height: auto;
        align: left top;
        padding-top: 1;
    }
    .hsv-row {
        width: 100%;
        height: 1;
        align: left middle;
    }
    .hsv-label {
        width: 11;
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
    #preview-column {
        width: 22;
        height: auto;
        align: left top;
        padding-top: 1;
    }
    #preview {
        width: 20;
        height: 10;
        background: #808080;
        border: none;
    }
    #readouts {
        width: 100%;
        height: auto;
        padding-top: 1;
    }
    .readout {
        width: 100%;
        height: 1;
        text-align: left;
        color: #b0b0b0;
    }
    #picker-actions {
        width: 100%;
        height: 3;
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

    #effect-modes {
        width: 100%;
        height: 1;
        align: left middle;
    }
    #effect-modes Button {
        width: auto;
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
    #effect-modes Button:hover {
        background: #1c1c1c;
        color: #ffffff;
    }
    #effect-modes Button.on {
        color: #ffffff;
        text-style: bold;
    }
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
    #power {
        dock: right;
        width: auto;
        height: 1;
        margin: 0 1 0 0;
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

    SavePresetScreen {
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
    """

    BINDINGS = [
        ("q", "quit", "Выход"),
        ("ctrl+c", "quit", None),
        ("ctrl+r", "refresh", "Обновить"),
    ]

    def compose(self) -> ComposeResult:
        yield VictusScreen()

    def action_refresh(self):
        tab = self.query_one("#kbd")
        tab._sync_controls()
        tab._set_status(t("tui.status_ready"))
