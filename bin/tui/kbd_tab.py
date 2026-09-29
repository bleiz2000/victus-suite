"""Вкладка «Подсветка» v2 — компактный Bento по новому ТЗ.

Слева  PRESETS            — быстрый список (12 базовых + свои цвета), «+ свой
                             цвет», внизу блока переключатели режимов и питание.
В центре COLOR PICKER      — HSV + RGB + Black Depth, поле HEX, внизу большое
                             квадратное превью и кнопки Apply / Copy HEX / Save.
Справа  LIGHTING EFFECTS   — Custom Effect Creator с живой синусоидой и
                             интерактивными стопами «+», Effect Speed,
                             Start / Stop.

Вся запись на клавиатуру идёт через фоновый демон (bin/victusd) по unix-сокету;
без демона TUI пишет напрямую через victus-kbd. Экран показывает ровно то, что
ушло в EC: демон отдаёт k/steps — тем же шагом крутится и синусоида.
"""

import asyncio
import os

from rich.cells import cell_len
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, Switch

from tui import core
from tui.slider import AsciiSlider, SineWave

import victus_log as vlog
import victus_palette as pal
from i18n import t

TOOL = "victus_tui"
_HERE = os.path.dirname(os.path.realpath(__file__))
_BIN = os.path.dirname(_HERE)
COLORMAKER = os.path.join(_BIN, "ColorMaker")

EFFECT_IDS = {"effect-none": "none", "effect-cycle": "cycle", "effect-fade": "fade"}
MODE_IDS = ("effect-none", "effect-cycle", "effect-fade")
MODE_NAMES = {
    "effect-none": t("tui.mode_static"),
    "effect-cycle": t("tui.mode_cycle"),
    "effect-fade": t("tui.mode_fade"),
}

NAME_WIDTH = 10
LABEL_WIDTH = 12


class RowButton(Button):
    """Кнопка без рамки и без внутренних отступов — строка списка."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.styles.line_pad = 0

    def get_content_width(self, container, viewport) -> int:
        lines = self.label.plain.splitlines()
        return max((cell_len(line) for line in lines), default=0)

    def on_mount(self) -> None:
        self.styles.line_pad = 0


def mode_label(mode_id: str, active: bool) -> str:
    mark = "*" if active else " "
    return f"[{mark}] {MODE_NAMES[mode_id]}"


def preset_label(name: str, rgb) -> Text:
    text = Text(f"{name:<{NAME_WIDTH}.{NAME_WIDTH}} ")
    text.append("[", style="dim")
    text.append("■", style=f"bold {core.to_hex(rgb)}")
    text.append("]", style="dim")
    return text


class SavePresetScreen(ModalScreen):
    """Диалог имени для [ Save Preset ] / «+ свой цвет»."""

    BINDINGS = [("escape", "cancel", None)]

    def __init__(self, hex_color: str):
        super().__init__()
        self.hex_color = hex_color

    def compose(self) -> ComposeResult:
        box = Vertical(id="save-box")
        box.border_title = t("tui.save_title")
        with box:
            yield Static(Text(f"Hex: [{self.hex_color}]"), id="save-hex", classes="readout")
            yield Input(placeholder=t("tui.name_placeholder"), id="name-input")
            with Horizontal(id="save-actions"):
                yield Button(Text(t("tui.btn_save")), id="save-ok")
                yield Button(Text(t("tui.btn_cancel")), id="save-cancel")

    def on_mount(self):
        self.query_one("#name-input", Input).focus()

    def _entered_name(self) -> str:
        return self.query_one("#name-input", Input).value.strip().lower()

    @on(Input.Submitted)
    def submitted(self, event):
        self.dismiss(self._entered_name() or None)

    @on(Button.Pressed)
    def pressed(self, event):
        bid = event.button.id
        if bid == "save-ok":
            self.dismiss(self._entered_name() or None)
        elif bid == "save-cancel":
            self.dismiss(None)

    def action_cancel(self):
        self.dismiss(None)


class PickColorScreen(ModalScreen):
    """Выбор цвета для одного из четырёх стопов синусоиды."""

    BINDINGS = [("escape", "cancel", None)]

    def __init__(self, index: int, current: str | None):
        super().__init__()
        self.index = index
        self.current = current

    def compose(self) -> ComposeResult:
        box = Vertical(id="pick-box")
        box.border_title = t("tui.pick_title", slot=self.index + 1)
        with box:
            listing = Vertical(id="pick-list")
            with listing:
                if self.current:
                    yield RowButton(Text(t("tui.pick_clear"), style="bold #ff6b6b"),
                                    id="p-clear", classes="preset")
                table = pal.all_colors()
                names = [n for n in core.QUICK if n in table]
                names += [n for n in sorted(table) if n not in core.QUICK]
                for name in names:
                    yield RowButton(preset_label(name, table[name]),
                                    id=f"p-{name}", classes="preset")

    def on_mount(self):
        first = self.query_one("#pick-list RowButton", RowButton)
        if first is not None:
            first.focus()

    @on(Button.Pressed)
    def pressed(self, event):
        bid = event.button.id or ""
        if bid.startswith("p-"):
            self.dismiss(bid[2:] or None)

    def action_cancel(self):
        self.dismiss(None)


class KbdTab(Vertical):
    power = reactive(True)
    color = reactive((255, 255, 255))
    effect = reactive("none")
    speed = reactive(1.0)
    black_depth = reactive(50)
    stops = reactive(None)
    running = reactive(False)
    # True, пока интерфейс пересобирается (смена языка): петлю не глушить
    _rebuilding = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        state = core.load_state()
        rgb = core._norm_rgb(state.get("rgb"), (255, 255, 255))
        self.color = tuple(rgb)
        self.power = bool(state.get("power", True))
        self.effect = state.get("effect", "none")
        self.speed = float(state.get("speed", 1.0))
        self.black_depth = int(state.get("black_depth", 50))
        self.stops = list(state.get("stops"))
        self.running = False  # старт всегда статичный: только ручной Start
        self._engine = core.Engine()
        self._push_timer = None
        self._syncing = False

    # --- композиция ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield from self._presets_panel()
            yield from self._color_panel()
            yield from self._effects_panel()
        with Horizontal(id="statusline"):
            with Horizontal(id="status-flow"):
                yield Static("", id="color-tag")
                yield Static("", id="status")

    def _presets_panel(self):
        panel = Vertical(classes="panel", id="presets-panel")
        panel.border_title = t("tui.sec_presets")
        with panel:
            yield RowButton(Text(t("tui.add_color")), id="add-color", classes="add-row")
            yield ScrollableContainer(id="preset-list")
            yield from self._mode_block()

    def _mode_block(self):
        block = Vertical(id="mode-block")
        with block:
            for mid in MODE_IDS:
                active = EFFECT_IDS[mid] == self.effect
                yield RowButton(
                    Text(mode_label(mid, active)),
                    id=mid,
                    classes=f"mode{' on' if active else ''}",
                )
            with Horizontal(classes="mode-row", id="power-row"):
                yield Label(t("tui.power"), classes="mode-label")
                yield Switch(value=self.power, id="power")
        return []

    def _color_panel(self):
        panel = Vertical(classes="panel", id="color-panel")
        panel.border_title = t("tui.sec_picker")
        with panel:
            with Vertical(id="picker-top"):
                yield from self._value_row("hue", t("tui.lab_hue"), 0, 360)
                yield from self._value_row("sat", t("tui.lab_sat"), 0, 100)
                yield from self._value_row("val", t("tui.lab_val"), 0, 100)
                yield from self._value_row("r", t("tui.lab_r"), 0, 255)
                yield from self._value_row("g", t("tui.lab_g"), 0, 255)
                yield from self._value_row("b", t("tui.lab_b"), 0, 255)
                yield from self._value_row("black", t("tui.lab_black"), 0, 100)
            with Horizontal(id="hex-row"):
                yield Label(t("tui.hex_label"), classes="mode-label")
                yield Input(value=core.to_hex(self.color), id="hex-input")
            with Horizontal(id="picker-bottom"):
                yield Static("", id="preview")
                with Vertical(id="bottom-right"):
                    with Vertical(id="readouts"):
                        yield Static("RGB", id="read-rgb", classes="readout")
                        yield Static("Hex", id="read-hex", classes="readout")
                        yield Static("", id="read-applied", classes="readout applied")
                    with Horizontal(id="picker-actions"):
                        yield Button(Text(t("tui.btn_apply")), id="apply")
                        yield Button(Text(t("tui.btn_copy_hex")), id="copy-hex")
                        yield Button(Text(t("tui.btn_save_preset")), id="save-name")

    def _value_row(self, sid, label, lo, hi):
        with Horizontal(classes="hsv-row", id=f"row-{sid}"):
            yield Label(label, classes="hsv-label")
            yield AsciiSlider(min=lo, max=hi, step=1, value=lo, id=sid)
            yield Static(f"{lo}", id=f"{sid}-val", classes="hsv-value")

    def _effects_panel(self):
        panel = Vertical(classes="panel", id="effects-panel")
        panel.border_title = t("tui.sec_effects")
        with panel:
            creator = Vertical(id="creator")
            creator.border_title = t("tui.sec_creator")
            with creator:
                yield SineWave(
                    slots=self.stops, base=self.color, speed=self.speed, id="sine"
                )
            with Horizontal(id="speed-row"):
                yield Static(
                    f"{t('tui.speed_label')} {self.speed:.1f}", id="speed-label"
                )
                yield AsciiSlider(
                    min=0.2, max=5.0, step=0.1, value=self.speed, id="speed"
                )
            with Horizontal(id="effect-actions"):
                yield Button(Text(t("tui.btn_start")), id="effect-start")
                yield Button(Text(t("tui.btn_stop")), id="effect-stop")

    # --- старт -----------------------------------------------------------------

    def on_mount(self):
        table = core.display_colors()
        listing = self.query_one("#preset-list", ScrollableContainer)
        names = list(table)
        selected = None
        for name in names:
            rgb = table[name]
            listing.mount(
                RowButton(preset_label(name, rgb), id=f"c-{name}", classes="preset")
            )
            if rgb == self.color and selected is None:
                selected = name
        self._mark_selected(selected)
        self._sync_controls()
        self._boot()
        self._poll = self.set_interval(0.3, self._poll_status)

    @work(exclusive=True, group="boot")
    async def _boot(self):
        # сначала проверяем доступ к EC: лучше сказать сразу, чем на клике
        access = await core.probe_access()
        if access in ("dry", "root", "direct", "sudo"):
            if await self._engine.ping():
                self._set_status(t("tui.status_daemon_on"))
            else:
                self._set_status(t("tui.status_ready"))
        elif access in ("need-password", "error"):
            # причина выбирается по факту: модуль есть/нет, а не по слову ошибки
            self._set_status(core.access_hint(access), error=True)

    async def _poll_status(self):
        st = await self._engine.status()
        if st is None:
            # демона нет: running держит сам TUI, синус живёт локальным таймером
            return
        if st.get("running"):
            steps = max(int(st.get("steps") or 1), 1)
            k = int(st.get("k") or 0)
            self.running = True
            wave = self.query_one("#sine", SineWave)
            wave.set_calm(False)
            wave.set_auto_flow(False)
            wave.set_color_step(k / steps)
            self._refresh_preview(core.hex_to_rgb(st.get("color")) or self.color)
        elif self.running:
            self.running = False
            self.query_one("#sine", SineWave).set_calm(True)
            self._refresh_preview(self.color)

    # --- состояние -------------------------------------------------------------

    def _state_payload(self) -> dict:
        return {
            "rgb": list(self.color),
            "hex": core.to_hex(self.color),
            "power": bool(self.power),
            "effect": self.effect,
            "speed": round(float(self.speed), 2),
            "stops": list(self.stops),
            "black_depth": int(self.black_depth),
        }

    async def _store(self):
        payload = self._state_payload()
        reply = await self._engine.push_state(payload)
        if reply is None:
            core.save_state(payload)
        return reply

    def _schedule_store(self, delay: float = 0.35):
        if self._push_timer is not None:
            self._push_timer.stop()
        self._push_timer = self.set_timer(delay, lambda: self.run_worker(self._store()))

    def _store_now(self):
        if self._push_timer is not None:
            self._push_timer.stop()
            self._push_timer = None
        return self._store()

    def _effective(self, color=None) -> tuple:
        base = tuple(color if color is not None else self.color)
        if not self.power:
            return (0, 0, 0)
        return core.apply_black_depth(base, self.black_depth)

    # --- отрисовка состояния ---------------------------------------------------

    def _set_status(self, text, error=False):
        st = self.query_one("#status", Static)
        st.update(Text(text))
        st.styles.color = "#ff6b6b" if error else "#7ee787"

    def _mark_selected(self, name):
        for btn in self.query(".preset"):
            btn.set_class(name is not None and btn.id == f"c-{name}", "selected")

    def _sync_controls(self):
        """Слайдеры, поле HEX и превью — по self.color / power / black_depth."""
        if self._syncing:
            return
        self._syncing = True
        try:
            h, s, v = pal.rgb_to_hsv(self.color)
            targets = {
                "hue": round(h),
                "sat": round(s * 100),
                "val": round(v * 100),
                "r": self.color[0],
                "g": self.color[1],
                "b": self.color[2],
                "black": self.black_depth,
            }
            for sid, value in targets.items():
                self.query_one(f"#{sid}", AsciiSlider).set_value(value)
                self.query_one(f"#{sid}-val", Static).update(str(value))
            hex_input = self.query_one("#hex-input", Input)
            if not hex_input.has_focus:
                hex_input.value = core.to_hex(self.color)
            wave = self.query_one("#sine", SineWave)
            wave.base = tuple(self.color)
            wave.set_slots(self.stops)
            wave.speed = self.speed
            self._refresh_readout()
        finally:
            self._syncing = False

    def _refresh_preview(self, applied=None):
        hexv = core.to_hex(applied if applied is not None else self._effective())
        self.query_one("#preview").styles.background = hexv
        self.query_one("#color-tag", Static).update(t("tui.color_tag", hex=hexv))

    def _refresh_readout(self):
        r, g, b = self.color
        raw = core.to_hex(self.color)
        applied = self._effective()
        applied_hex = core.to_hex(applied)
        self.query_one("#read-rgb", Static).update(Text(f"RGB {r},{g},{b}"))
        self.query_one("#read-hex", Static).update(Text(f"Hex {raw}"))
        extra = self.query_one("#read-applied", Static)
        if applied_hex != raw:
            extra.update(Text(f"→ {applied_hex}", style="bold #7ee787"))
        else:
            extra.update(Text(""))
        self._refresh_preview(applied)

    def _set_color(self, color, select: str | None = None):
        self.color = tuple(core._norm_rgb(color, self.color))
        if select is None:
            table = core.display_colors()
            select = next(
                (n for n, v in table.items() if tuple(v) == tuple(self.color)), None
            )
        self._mark_selected(select)
        self._sync_controls()
        self._schedule_store()

    # --- действия ---------------------------------------------------------------

    async def _apply_current(self):
        # ручной цвет всегда побеждает: снимаем любую фоновую петлю,
        # даже если TUI про неё не знает (демон/чужой процесс мог её завести)
        self.running = False
        await self._engine.kill_loop()
        self.query_one("#sine", SineWave).set_calm(True)
        await self._store_now()
        color = self._effective()
        success, msg = await self._engine.apply(self.color, color)
        if not success:
            self._set_status(msg or t("tui.apply_failed", rc=1), error=True)
            vlog.log_error(TOOL, f"apply failed: {msg}", exc=False)
            return
        self._set_status(t("tui.applied", color=core.to_hex(color)))
        self._refresh_preview(color)

    async def _select_preset(self, name):
        rgb = pal.all_colors().get(name)
        if rgb is None:
            return
        self.power = True
        self.query_one("#power", Switch).value = True
        self._set_color(rgb, select=name)
        await self._apply_current()

    def _gradient_colors(self) -> list:
        return core.colors_for_state(self._state_payload())

    async def _start_effect(self):
        if self.effect == "none":
            self._set_status(t("tui.effect_none_status"))
            return
        if not self.power:
            self.power = True
            self.query_one("#power", Switch).value = True
        await self._store_now()
        colors = self._gradient_colors()
        delay = core.delay_for_speed(self.speed)
        # на всякий случай гасим чужую петлю — Start должен завестись всегда
        if not self._engine.online:
            await core.local_effect_stop()
        ok, msg = await self._engine.effect_start(colors, delay, self.effect)
        if not ok:
            self._set_status(msg or t("tui.effect_failed", rc=1), error=True)
            vlog.log_error(TOOL, f"effect start failed: {msg}", exc=False)
            return
        self.running = True
        wave = self.query_one("#sine", SineWave)
        wave.set_calm(False)
        wave.set_auto_flow(not self._engine.online)
        self._set_status(msg or t("tui.effect_started"))
        if self._engine.online:
            await self._poll_status()

    async def _stop_effect(self):
        ok, msg = await self._engine.effect_stop()
        self.running = False
        self.query_one("#sine", SineWave).set_calm(True)
        self._set_status(msg or t("tui.effect_stopped"))
        await self._store_now()

    @work(exclusive=True)
    async def _prompt_save(self):
        result = await self.app.push_screen(
            SavePresetScreen(core.to_hex(self.color)), wait_for_dismiss=True
        )
        if result:
            await self._save_named_color(str(result))

    @work(exclusive=True)
    async def _pick_stop(self, index: int):
        result = await self.app.push_screen(
            PickColorScreen(index, self.stops[index]), wait_for_dismiss=True
        )
        vlog.log_info(TOOL, f"pick result slot={index} result={result!r}")
        if result is None:
            return
        if result == "clear":
            self.stops[index] = None
        else:
            rgb = pal.all_colors().get(str(result))
            if rgb is None:
                return
            self.stops[index] = core.to_hex(rgb)
        self.stops = list(self.stops)
        self._sync_controls()
        if self.running:
            await self._store_now()
        else:
            self._schedule_store()

    async def _save_named_color(self, name):
        if not pal.NAME_RE.match(name):
            self._set_status(t("cm.name_rule"), error=True)
            return
        proc = await asyncio.create_subprocess_exec(
            COLORMAKER,
            "add",
            name,
            core.to_hex(self.color),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            self._set_status(
                err.decode().strip() or t("tui.apply_failed", rc=proc.returncode),
                error=True,
            )
            return
        self._set_status(out.decode().strip() or t("tui.saved"))
        vlog.log_info(TOOL, f"saved color {name}={self.color}")
        self._refresh_presets()

    def _refresh_presets(self):
        listing = self.query_one("#preset-list", ScrollableContainer)
        table = core.display_colors()
        names = list(table)
        for btn in list(listing.query(".preset")):
            btn.remove()
        selected = None
        for name in names:
            rgb = table[name]
            listing.mount(
                RowButton(preset_label(name, rgb), id=f"c-{name}", classes="preset")
            )
            if tuple(rgb) == tuple(self.color) and selected is None:
                selected = name
        self._mark_selected(selected)

    # --- события ----------------------------------------------------------------

    @on(AsciiSlider.Changed)
    def slider_changed(self, event):
        if self._syncing:
            return
        sid = event.slider.id
        value = round(event.value)
        if sid == "black":
            self.black_depth = value
            self.query_one("#black-val", Static).update(str(value))
            self._refresh_readout()
            self._schedule_store()
            if self.running:
                self.run_worker(self._store_now(), exclusive=False)
            return
        if sid == "speed":
            self.speed = round(event.value, 1)
            self.query_one("#speed-label", Static).update(
                f"{t('tui.speed_label')} {self.speed:.1f}"
            )
            self.query_one("#sine", SineWave).speed = self.speed
            self._schedule_store()
            if self.running:
                self.run_worker(self._store_now(), exclusive=False)
            return
        if sid in ("hue", "sat", "val"):
            hue = self.query_one("#hue", AsciiSlider).value
            sat = self.query_one("#sat", AsciiSlider).value / 100.0
            val = self.query_one("#val", AsciiSlider).value / 100.0
            self._set_color(pal.hsv_to_rgb(hue, sat, val))
        elif sid in ("r", "g", "b"):
            rgb = [
                self.query_one(f"#{k}", AsciiSlider).value for k in ("r", "g", "b")
            ]
            self._set_color(rgb)

    @on(SineWave.StopClicked)
    def stop_clicked(self, event):
        self._pick_stop(event.index)

    @on(Input.Submitted)
    def input_submitted(self, event):
        if event.input.id != "hex-input":
            return
        rgb = core.hex_to_rgb(event.value)
        if rgb is None:
            self._set_status(t("tui.bad_hex", value=event.value), error=True)
            return
        self._set_color(rgb)
        self.run_worker(self._apply_current(), exclusive=True)

    @work(exclusive=True)
    async def _power_changed(self, on: bool):
        self.power = bool(on)
        if not on:
            self.running = False
            await self._stop_effect()
        self._refresh_readout()
        await self._apply_current()

    def on_switch_changed(self, event):
        if event.switch.id != "power":
            return
        self._power_changed(bool(event.value))

    def _set_effect(self, mode_id):
        if mode_id not in EFFECT_IDS:
            return
        self.effect = EFFECT_IDS[mode_id]
        for mid in MODE_IDS:
            btn = self.query_one(f"#{mid}", Button)
            active = mid == mode_id
            btn.label = Content.from_text(Text(mode_label(mid, active)))
            btn.set_class(active, "on")
        self._schedule_store()

    async def on_button_pressed(self, event):
        bid = event.button.id or ""
        if bid in EFFECT_IDS:
            self._set_effect(bid)
        elif bid.startswith("c-"):
            await self._select_preset(bid[2:])
        elif bid == "apply":
            await self._apply_current()
        elif bid == "effect-start":
            await self._start_effect()
        elif bid == "effect-stop":
            await self._stop_effect()
        elif bid == "copy-hex":
            hexv = core.to_hex(self._effective())
            try:
                self.app.copy_to_clipboard(hexv)
                self._set_status(t("tui.copied", hex=hexv))
            except Exception as e:  # noqa: BLE001
                vlog.log("warn", TOOL, f"clipboard failed: {e}")
                self._set_status(hexv)
        elif bid == "save-name" or bid == "add-color":
            self._prompt_save()

    def on_unmount(self):
        if self._push_timer is not None:
            self._push_timer.stop()
        timer = getattr(self, "_poll", None)
        if timer is not None:
            timer.stop()
        # закрыли окно → петля не должна остаться крутиться фоном;
        # при пересборке под смену языка петля продолжает работать
        if self.running and not KbdTab._rebuilding:
            core.stop_effect_sync()
            vlog.log_info(TOOL, "window closed — effect stopped")

    def restore_running(self):
        """Вернуть признак работающей петли после пересборки интерфейса."""
        self.running = True
        self.query_one("#sine", SineWave).set_calm(False)
