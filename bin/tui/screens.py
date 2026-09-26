"""Root screen and App of victus_tui.

Tabs follow the approved mockup; only «Подсветка» exists now —
fans/power tabs are later stages and are not created.
"""

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, TabbedContent, TabPane

from i18n import t
from tui.kbd_tab import KbdTab


class VictusScreen(Container):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            yield TabPane(t("tui.tab_kbd"), KbdTab(id="kbd"))
        yield Footer()


class VictusApp(App):
    TITLE = "victus-suite"
    CSS_PATH = None
    CSS = """
    Screen {
        background: $surface;
    }
    .top-row {
        height: 3;
        align: left middle;
        padding: 0 2;
    }
    .row-label {
        width: auto;
        padding: 0 2 0 0;
        content-align: left middle;
    }
    #current-color {
        width: auto;
        padding: 0 1;
        text-style: bold;
        color: $accent;
    }
    .section-title {
        height: auto;
        padding: 1 2 0 2;
        text-style: bold;
        color: $accent;
    }
    #palette-scroll {
        height: 11;
        padding: 0 1;
    }
    #palette {
        grid-size: 8;
        grid-gutter: 1 2;
        height: auto;
    }
    .swatch {
        width: 14;
        height: 1;
        border: none;
    }
    .picker {
        height: auto;
        padding: 0 2;
    }
    .row, .effects-row {
        height: auto;
    }
    .slider-row {
        height: 2;
        align: left middle;
    }
    .slider-label {
        width: 14;
    }
    .slider-row MiniSlider {
        width: 1fr;
        height: 1;
    }
    .slider-value {
        width: 8;
        text-align: right;
    }
    #swatch {
        height: 4;
        width: 100%;
        border: heavy $accent;
        text-align: center;
    }
    .readout {
        width: 1fr;
        text-align: center;
        color: $text-muted;
    }
    #name-input {
        width: 24;
    }
    .status {
        height: 2;
        padding: 1 2 0 2;
        color: #7ee787;
    }
    .speed-box {
        width: 1fr;
        height: auto;
        padding-left: 2;
    }
    RadioSet {
        width: 42;
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
