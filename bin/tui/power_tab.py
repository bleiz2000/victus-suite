"""Вкладка «Питание» — режимы электропитания и тумблер «Печатная машинка».

Минималистично, как и остальные вкладки: одна панель с тумблером, чипом
состояния (ВКЛ / выкл / частично), списком показаний и строкой статуса.

Главное правило вкладки: **индикатор показывает железо, а не клик.**
`tui.power_core.mode()` определяет режим по root-снимку и жёстким ручкам
(no_turbo, PL1), поэтому после сбоя, ручного `victus-power restore` или
частичного apply тумблер и чип перестраиваются сами — «плавающих»
и ложных состояний нет. Неудачный переключатель возвращается на место.

Вся логика — в `tui.power_core`: PPD и герцовка без root, вентиляторы через
NOPASSWD `victus-kbd`, частоты/turbo/RAPL/дискретка/MUX/радио через NOPASSWD
`victus-power`. Показания обновляются раз в 5 с, переключение идёт в воркере
и не блокирует интерфейс.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Label, Static, Switch

from tui import core, power_core

import victus_log as vlog
from i18n import t

TOOL = "power"
POLL_S = 5.0

MODE_LABELS = {
    power_core.MODE_TYPEWRITER: "tui.pwr_state_on",
    power_core.MODE_PARTIAL: "tui.pwr_state_partial",
    power_core.MODE_NORMAL: "tui.pwr_state_off",
}
MODE_CLASSES = {
    power_core.MODE_TYPEWRITER: "on",
    power_core.MODE_PARTIAL: "warn",
    power_core.MODE_NORMAL: "",
}


def _fmt_dur(hours) -> str:
    """3.22 → «3 ч 13 мин»; 0.4 → «24 мин»; 61 → «2 дн 13 ч»."""
    if hours is None or hours <= 0:
        return "-"
    total = int(round(hours * 60))
    if hours >= 48:
        return t("tui.pwr_dur_days", d=total // 1440, h=(total % 1440) // 60)
    if hours < 1:
        return t("tui.pwr_dur_min", m=max(1, total))
    return t("tui.pwr_dur", h=total // 60, m=total % 60)


def _fmt_hz(hz) -> str:
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return "-"
    return "%d" % hz if abs(hz - round(hz)) < 0.05 else "%.1f" % hz


class WattsBar(Static):
    """Ползунок потолка мощности CPU 5..25 Вт.

    В Textual 8.2.8 встроенного Slider нет (в `textual.widgets` он
    отсутствует), поэтому рисуем свой: клик по дорожке, ←/→ и ↑/↓ на 1 Вт,
    PgUp/PgDn на 5 Вт, Home/End — к краям. Программная запись `.value =`
    события не шлёт — Changed появляется только от рук пользователя.
    """
    MIN, MAX = 5, 25
    can_focus = True
    value = reactive(15)

    class Changed(Message):
        def __init__(self, bar: "WattsBar", value: int) -> None:
            super().__init__()
            self.bar = bar
            self.value = value

    def render(self):
        span = max(8, (self.size.width or 40) - 7)
        frac = (self.value - self.MIN) / (self.MAX - self.MIN)
        n = max(0, min(span, int(round(frac * span))))
        return Text("%s %2d Вт" % ("█" * n + "░" * (span - n), self.value))

    def _set(self, want, notify: bool = True) -> None:
        want = max(self.MIN, min(self.MAX, int(want)))
        if want == self.value:
            return
        self.value = want
        if notify:
            self.post_message(self.Changed(self, want))

    def on_click(self, event: events.Click) -> None:
        self.focus()
        span = max(1, (self.size.width or 40) - 7)
        frac = max(0.0, min(1.0, event.offset.x / float(span)))
        self._set(self.MIN + round(frac * (self.MAX - self.MIN)))

    def on_key(self, event: events.Key) -> None:
        deltas = {"left": -1, "down": -1, "right": 1, "up": 1,
                  "pagedown": -5, "pageup": 5}
        if event.key in deltas:
            self._set(self.value + deltas[event.key])
            event.stop()
        elif event.key == "home":
            self._set(self.MIN); event.stop()
        elif event.key == "end":
            self._set(self.MAX); event.stop()

    def on_scroll_up(self, event: events.ScrollUp) -> None:
        self._set(self.value + 1)

    def on_scroll_down(self, event: events.ScrollDown) -> None:
        self._set(self.value - 1)


class PowerTab(Vertical):
    typewriter = reactive(False)
    _rebuilding = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        state = core.load_state()
        self.typewriter = state.get("power_mode") == "typewriter"
        self._st = {}
        self._busy = False
        self._mode_busy = False
        self._poll = None
        self._watts_syncing = False
        self._watts_applied = 15
        self._watts_pending = None

    # --- композиция ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="pbody"):
            panel = Vertical(classes="panel", id="pcontrol")
            panel.border_title = t("tui.sec_power")
            with panel:
                with Vertical(id="p-mode-block"):
                    with Horizontal(classes="mode-row", id="pwr-row"):
                        yield Label(t("tui.pwr_typewriter"), classes="mode-label")
                        # чип — состояние ЖЕЛЕЗА, не последний клик
                        yield Static(t("tui.pwr_state_off"), id="pwr-state")
                        yield Switch(value=self.typewriter, id="pwr-switch")
                    yield Static(self._hint(), id="pwr-hint", classes="vblock")
                    with Vertical(classes="vblock", id="pwr-watts-block"):
                        yield Static("", id="pwr-watts-cap")
                        yield WattsBar(id="pwr-watts")
                        yield Static(t("tui.pwr_watts_off"), id="pwr-watts-hint")
                with Vertical(id="p-readouts"):
                    yield Static("", id="p-lines", classes="vblock")
        with Horizontal(id="pstatusline"):
            with Horizontal(id="pstatus-flow"):
                yield Static("", id="pstatus-tag")
                yield Static("", id="pstatus")

    def _hint(self) -> str:
        return (t("tui.pwr_hint_typewriter") if self.typewriter
                else t("tui.pwr_hint_full"))

    # --- старт --------------------------------------------------------------

    def on_mount(self):
        self._render_lines(self._st)
        self._boot()
        self._poll = self.set_interval(POLL_S, self._tick)

    @work(exclusive=True, group="power-boot")
    async def _boot(self):
        st = await asyncio.to_thread(power_core.status)
        self._sync(st)
        if not st.get("root_ok"):
            self._set_status(t("tui.pwr_need_sudo"), error=True)
        else:
            self._set_status(t("tui.pwr_ready"))

    @work(exclusive=True, group="power-tick")
    async def _tick(self):
        if self._busy:                      # не мешаем идущему переключению
            return
        try:
            st = await asyncio.to_thread(power_core.status)
        except Exception as e:              # noqa: BLE001
            vlog.log("warn", TOOL, f"status failed: {e}")
            return
        self._sync(st)                      # в т.ч. перетягивает тумблер

    # --- синхронизация UI с железом -----------------------------------------

    def _sync(self, st: dict, announce: str | None = None,
              error: bool = False, warn: bool = False) -> None:
        """Единственная точка, которая двигает чип/тумблер/подсказку/state."""
        self._st = st or {}
        mode = self._st.get("mode") or power_core.MODE_NORMAL
        on = mode != power_core.MODE_NORMAL

        # сначала атрибут, потом .value: событие Switch уйдёт с уже
        # согласованным значением и не вызовет повторный переключатель
        self.typewriter = on
        chip = self.query_one("#pwr-state", Static)
        chip.remove_class("on", "warn")
        cls = MODE_CLASSES.get(mode, "")
        if cls:
            chip.add_class(cls)
        chip.update(Text(t(MODE_LABELS.get(mode, "tui.pwr_state_off"))))

        sw = self.query_one("#pwr-switch", Switch)
        if not self._busy and sw.value != on:
            sw.value = on

        # раньше тут стояли ключи hint_on/hint_off «наоборот»: чип гордо
        # показывал ВКЛ, а подпись под ним — «полная мощность, турбо, 144 Гц»
        # при реальных 15 Вт и 60 Гц
        self.query_one("#pwr-hint", Static).update(Text(
            t("tui.pwr_hint_typewriter")
            if mode == power_core.MODE_TYPEWRITER
            else t("tui.pwr_hint_full")))
        self._sync_watts(st, mode)
        self._render_lines(self._st)

        # состояние на диске должно отражать железо, а не последний клик
        try:
            state = core.load_state()
            want = "typewriter" if on else "normal"
            if state.get("power_mode") != want:
                state["power_mode"] = want
                core.save_state(state)
        except OSError as exc:
            vlog.log("warn", TOOL, f"save state failed: {exc}")

        if announce is not None:
            self._set_status(announce, error=error, warn=warn)

    # --- переключатель ------------------------------------------------------

    @work(exclusive=True, group="power-toggle")
    async def _toggle(self, on: bool):
        if self._busy:
            return
        self._busy = True
        self._mode_busy = True
        sw = self.query_one("#pwr-switch", Switch)
        sw.disabled = True                   # никаких повторных кликов в полёте
        self._set_status(t("tui.pwr_applying"))
        try:
            res = await asyncio.to_thread(power_core.set_typewriter, on)
        except Exception as e:               # noqa: BLE001
            vlog.log("warn", TOOL, f"toggle failed: {e}")
            st = await asyncio.to_thread(power_core.status)
            # тумблер возвращается туда, где реально железо
            self._sync(st, announce=t("tui.pwr_failed", msg=str(e)[:80]),
                       error=True)
            self._busy = False
            self._mode_busy = False
            sw.disabled = False
            return

        st = res.get("status")
        if not isinstance(st, dict):
            st = await asyncio.to_thread(power_core.status)
        mode = st.get("mode") or power_core.MODE_NORMAL
        failed = res.get("failed") or []
        actual = mode != power_core.MODE_NORMAL

        if failed:
            announce, error, warn = t("tui.pwr_failed", msg=failed[0][:80]), True, False
        elif on and mode == power_core.MODE_PARTIAL:
            announce, error, warn = t("tui.pwr_partial"), False, True
        elif actual != on:
            # хотели включить — система осталась выключенной (и наоборот)
            announce, error, warn = t("tui.pwr_desync"), True, False
        else:
            announce = t("tui.pwr_on_ok") if on else t("tui.pwr_off_ok")
            error, warn = False, False

        self._busy = False
        self._mode_busy = False
        self._sync(st, announce=announce, error=error, warn=warn)
        sw.disabled = False

    def on_switch_changed(self, event):
        if event.switch.id != "pwr-switch" or self._busy:
            return
        want = bool(event.value)
        if want == self.typewriter:
            return                          # это мы сами перетянули тумблер
        self._toggle(want)

    # --- ползунок потолка мощности -----------------------------------------

    def _sync_watts(self, st: dict, mode: str) -> None:
        """Слайдер 5..25 Вт: работает ТОЛЬКО при включённой печатной
        машинке, значение тянется из железа (rapl_pl1), а не из последнего
        перетаскивания."""
        try:
            sl = self.query_one("#pwr-watts", WattsBar)
            cap = self.query_one("#pwr-watts-cap", Static)
            hint = self.query_one("#pwr-watts-hint", Static)
        except Exception:                                  # noqa: BLE001
            return
        # гасим только на время переворота тумблера: _busy включается и при
        # записи RAPL, а если погасить ползунок в этот момент, Textual снимет
        # с него фокус — и серия «стрелка→» вырождается в одно нажатие
        on = mode == power_core.MODE_TYPEWRITER and not self._mode_busy
        # status() кладёт корневой снимок в st["root"]
        pl1 = (st.get("root") or {}).get("rapl_pl1_w")
        try:
            want = max(5, min(25, int(round(float(pl1)))))
        except (TypeError, ValueError):
            want = 15
        cap.update(Text(t("tui.pwr_watts_lbl")))
        hint.update(Text(t("tui.pwr_watts_now", n=want) if on
                         else t("tui.pwr_watts_off")))
        if abs(float(sl.value) - want) > 0.5:
            # это значение подтянуто из железа, а не перетянуто рукой
            self._watts_syncing = True
            try:
                sl.value = want
                self._watts_applied = want
            finally:
                self._watts_syncing = False
        sl.disabled = not on

    def on_watts_bar_changed(self, event: WattsBar.Changed):
        if self._busy or self._watts_syncing:
            return
        if (self._st or {}).get("mode") != power_core.MODE_TYPEWRITER:
            return                      # режим выключен — ползунок мёртв
        want = int(event.value)
        if want == self._watts_applied:
            return                      # это мы сами подтянули из железа
        if self._busy:
            # правка пришла, пока root ещё пишет прошлое значение:
            # запоминаем и применяем последней, а не выбрасываем (иначе
            # серия быстрых «стрелка→» вырождается в одно нажатие)
            self._watts_pending = want
            return
        self._apply_watts(want)

    @work(exclusive=True, group="power-watts")
    async def _apply_watts(self, want: int):
        self._busy = True
        # ползунок НЕ блокируем: он остаётся живым и копит _watts_pending
        self._watts_pending = None
        self._set_status(t("tui.pwr_watts_apply", n=want))
        try:
            res = await asyncio.to_thread(power_core.set_watt_limit, want)
        except Exception as e:                              # noqa: BLE001
            vlog.log("warn", TOOL, f"watts failed: {e}")
            st = await asyncio.to_thread(power_core.status)
            self._watts_applied = int(round(float(
                ((st.get("root") or {}).get("rapl_pl1_w")) or want)))
            self._busy = False
            self._sync(st, announce=t("tui.pwr_watts_fail", msg=str(e)[:80]),
                       error=True)
            self._rerun_pending()
            return
        st = res.get("status") or await asyncio.to_thread(power_core.status)
        failed = res.get("failed") or []
        self._watts_applied = int(round(float(
            ((st.get("root") or {}).get("rapl_pl1_w")) or want)))
        self._busy = False
        if failed:
            self._sync(st, announce=t("tui.pwr_watts_fail", msg=failed[0][:80]),
                       error=True)
        else:
            self._sync(st, announce=t("tui.pwr_watts_ok",
                                      n=self._watts_applied))
        self._rerun_pending()

    def _rerun_pending(self) -> None:
        """Догоняем значение, которое пользователь выставил, пока шла запись."""
        want = self._watts_pending
        self._watts_pending = None
        if want is not None and want != self._watts_applied:
            self._apply_watts(want)

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
        pl1 = root.get("rapl_pl1_w")
        pl1s = t("tui.pwr_watts", n=pl1) if pl1 is not None else "-"
        freq = root.get("max_freq_mhz")
        lines = [
            self._line(t("tui.pwr_profile"),
                       "%s · platform %s" % (st.get("ppd") or "-",
                                             root.get("platform_profile") or "-")),
            self._line(t("tui.pwr_cpu"),
                       "%s · %s · turbo %s · PL1 %s · %s" % (
                           root.get("governor") or "-",
                           root.get("epp") or "-",
                           t("tui.pwr_turbo_off")
                           if str(root.get("no_turbo")) == "1"
                           else t("tui.pwr_turbo_on"),
                           pl1s,
                           t("tui.pwr_mhz", n=freq)
                           if freq is not None else "-")),
            self._line(t("tui.pwr_screen"),
                       t("tui.pwr_hz", n=_fmt_hz(mon.get("hz")))),
            self._line(t("tui.pwr_gpu"),
                       "%s · MUX %s · %s" % (
                           root.get("dgpu_runtime") or "-",
                           {"0": "hybrid", "1": "discrete", "2": "advanced"}.get(
                               str(root.get("mux")), str(root.get("mux") or "-")),
                           # спящую карту не опрашиваем (иначе разбудим)
                           t("tui.pwr_gpu_asleep")
                           if root.get("dgpu_runtime") == "suspended"
                           else (t("tui.pwr_gpu_limit",
                                   n=root["nvidia_pl_w"])
                                 if root.get("nvidia_pl_w") is not None
                                 else "-"))),
            self._line(t("tui.pwr_radio"),
                       "wifi save=%s · bt %s" % (
                           root.get("wifi_power_save") or "-",
                           "blocked" if root.get("bt_soft") == "yes"
                           else ("unblocked" if root.get("bt_soft") == "no" else "-"))),
            self._line(t("tui.pwr_fans"),
                       "%s · %s/%s RPM" % (fans.get("mode_name") or "-",
                                           fans.get("fan1") or "-",
                                           fans.get("fan2") or "-")),
            self._line(t("tui.pwr_bat"), self._battery_line(bat)),
        ]
        widget.update(self._join(lines))

    @staticmethod
    def _battery_line(bat: dict) -> str:
        """100% · Discharging · 14.7 Вт · ≈ 3 ч 13 мин — измеренное."""
        parts = ["%s%%" % (bat.get("capacity") or "-"),
                 bat.get("status") or "-"]
        if bat.get("watts"):
            parts.append(t("tui.pwr_watts", n=("%.1f" % bat["watts"])
                           .rstrip("0").rstrip(".")))
        if bat.get("hours"):
            parts.append("≈ " + _fmt_dur(bat["hours"]))
        return " · ".join(parts)

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

    def _set_status(self, text, error=False, warn=False):
        widget = self.query_one("#pstatus", Static)
        widget.update(Text(str(text)))
        widget.styles.color = ("#ff6b6b" if error
                               else "#ffd766" if warn else "#7ee787")

    def on_unmount(self):
        if self._poll is not None:
            self._poll.stop()
