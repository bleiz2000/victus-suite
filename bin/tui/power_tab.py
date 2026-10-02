"""Вкладка «Питание» — режимы электропитания и тумблер «Печатная машинка».

Минималистично, как и остальные вкладки: одна панель с тумблером и списком
показаний, строка статуса снизу. Вся логика — в `tui.power_core`:
PPD и герцовка без root, вентиляторы через NOPASSWD `victus-kbd`,
частоты/turbo/RAPL/дискретка/MUX через NOPASSWD `victus-power`.

Показания обновляются раз в 5 с; операция переключения идёт в воркере,
интерфейс в это время не блокируется.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Label, Static, Switch

from tui import core, power_core

import victus_log as vlog
from i18n import t

TOOL = "power"
POLL_S = 5.0


def _fmt_hz(hz) -> str:
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return "-"
    return "%d" % hz if abs(hz - round(hz)) < 0.05 else "%.1f" % hz


class PowerTab(Vertical):
    typewriter = reactive(False)
    _rebuilding = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        state = core.load_state()
        self.typewriter = state.get("power_mode") == "typewriter"
        self._st = {}
        self._busy = False
        self._poll = None

    # --- композиция ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="pbody"):
            panel = Vertical(classes="panel", id="pcontrol")
            panel.border_title = t("tui.sec_power")
            with panel:
                with Vertical(id="p-mode-block"):
                    with Horizontal(classes="mode-row", id="pwr-row"):
                        yield Label(t("tui.pwr_typewriter"), classes="mode-label")
                        yield Switch(value=self.typewriter, id="pwr-switch")
                    yield Static(self._hint(), id="pwr-hint", classes="vblock")
                with Vertical(id="p-readouts"):
                    yield Static("", id="p-lines", classes="vblock")
        with Horizontal(id="pstatusline"):
            with Horizontal(id="pstatus-flow"):
                yield Static("", id="pstatus-tag")
                yield Static("", id="pstatus")

    def _hint(self) -> str:
        return t("tui.pwr_hint_on") if self.typewriter else t("tui.pwr_hint_off")

    # --- старт --------------------------------------------------------------

    def on_mount(self):
        self._render_lines(self._st)
        self._boot()
        self._poll = self.set_interval(POLL_S, self._tick)

    @work(exclusive=True, group="power-boot")
    async def _boot(self):
        st = await asyncio.to_thread(power_core.status)
        self._st = st
        if not st.get("root_ok"):
            self._set_status(t("tui.pwr_need_sudo"), error=True)
        else:
            self._set_status(t("tui.pwr_ready"))
        self._render_lines(st)

    @work(exclusive=True, group="power-tick")
    async def _tick(self):
        if self._busy:                      # не мешаем идущему переключению
            return
        try:
            st = await asyncio.to_thread(power_core.status)
        except Exception as e:              # noqa: BLE001
            vlog.log("warn", TOOL, f"status failed: {e}")
            return
        self._st = st
        self._render_lines(st)

    # --- переключатель ------------------------------------------------------

    @work(exclusive=True, group="power-toggle")
    async def _toggle(self, on: bool):
        self._busy = True
        self._set_status(t("tui.pwr_applying"))
        try:
            res = await asyncio.to_thread(power_core.set_typewriter, on)
        except Exception as e:              # noqa: BLE001
            vlog.log("warn", TOOL, f"toggle failed: {e}")
            self._set_status(t("tui.pwr_failed", msg=str(e)[:80]), error=True)
            self._busy = False
            return

        failed = res.get("failed") or []
        if failed:
            self._set_status(t("tui.pwr_failed", msg=failed[0][:80]), error=True)
        else:
            self.typewriter = on
            state = core.load_state()
            state["power_mode"] = "typewriter" if on else "normal"
            core.save_state(state)
            self._set_status(t("tui.pwr_on_ok" if on else "tui.pwr_off_ok"))
        hint = self.query_one("#pwr-hint", Static)
        hint.update(Text(self._hint()))
        self._render_lines(res.get("status") or self._st)
        self._busy = False

    def on_switch_changed(self, event):
        if event.switch.id != "pwr-switch":
            return
        want = bool(event.value)
        if want == self.typewriter:
            return
        self._toggle(want)

    # --- отрисовка ----------------------------------------------------------

    def _render_lines(self, st: dict) -> None:
        widget = self.query_one("#p-lines", Static)
        if not st:
            widget.update(Text(t("tui.pwr_wait"), style="#7a7a7a"))
            return
        root = st.get("root") or {}
        mon = st.get("monitor") or {}
        fans = st.get("fans") or {}
        bat = st.get("battery") or {}
        lines = [
            self._line(t("tui.pwr_profile"),
                       "%s · platform %s" % (st.get("ppd") or "-",
                                             root.get("platform_profile") or "-")),
            self._line(t("tui.pwr_cpu"),
                       "%s · %s · turbo %s · PL1 %s Вт" % (
                           root.get("governor") or "-",
                           root.get("epp") or "-",
                           "выкл" if str(root.get("no_turbo")) == "1" else "вкл",
                           root.get("rapl_pl1_w") if root.get("rapl_pl1_w") is not None else "-")),
            self._line(t("tui.pwr_screen"), "%s Гц" % _fmt_hz(mon.get("hz"))),
            self._line(t("tui.pwr_gpu"),
                       "%s · MUX %s · лимит %s Вт" % (
                           root.get("dgpu_runtime") or "-",
                           {"0": "hybrid", "1": "discrete", "2": "advanced"}.get(
                               str(root.get("mux")), str(root.get("mux") or "-")),
                           root.get("nvidia_pl_w") if root.get("nvidia_pl_w") is not None else "-")),
            self._line(t("tui.pwr_fans"),
                       "%s · %s/%s RPM" % (fans.get("mode_name") or "-",
                                           fans.get("fan1") or "-",
                                           fans.get("fan2") or "-")),
            self._line(t("tui.pwr_bat"),
                       "%s%% · %s" % (bat.get("capacity") or "-",
                                      bat.get("status") or "-")),
        ]
        widget.update(self._join(lines))

    @staticmethod
    def _line(label: str, value: str) -> Text:
        text = Text()
        text.append("%-12s " % label, style="#8a8a8a")
        text.append(value, style="#e8e8e8")
        return text

    @staticmethod
    def _join(lines) -> Text:
        out = Text()
        for i, line in enumerate(lines):
            if i:
                out.append("\n")
            out.append(line)
        return out

    def _set_status(self, text, error=False):
        widget = self.query_one("#pstatus", Static)
        widget.update(Text(str(text)))
        widget.styles.color = "#ff6b6b" if error else "#7ee787"

    def on_unmount(self):
        if self._poll is not None:
            self._poll.stop()
