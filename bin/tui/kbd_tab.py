"""Вкладка «Подсветка» v1.2 — три панели по утверждённому макету.

Слева  PRESETS            — вертикальный список цветов с квадратом превью.
В центре COLOR PICKER      — ASCII-слайдеры Hue/Saturation/Brightness,
                             квадратный (1:1) предпросмотр, H/S/V/Hex,
                             кнопки [ Apply ] [ Copy HEX ] [ Save Preset ].
Справа  LIGHTING EFFECTS   — режимы [ ] Static [*] Cycle [ ] Fade,
                             Custom Effect Creator с синусоидой,
                             Effect Speed, [ Start ] / [ Stop ].

TUI = обёртка над CLI: запись цвета/эффектов идёт только через victus-kbd,
палитра — через victus_palette (без дублей). Состояние: state/last_state.json.

Слайдеры рисуют предпросмотр, в EC цвет уходит только по явному действию:
«Apply», клик пресета, Вкл/Выкл, «Start» эффекта.
"""

import asyncio
import datetime
import json
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

from tui.slider import AsciiSlider, SineWave

import victus_log as vlog
import victus_palette as pal
from i18n import t

TOOL = "victus_tui"
_HERE = os.path.dirname(os.path.realpath(__file__))
_BIN = os.path.dirname(_HERE)
BACKEND = os.path.join(_BIN, "victus-kbd")
COLORMAKER = os.path.join(_BIN, "ColorMaker")

STATE_FILE = os.path.join(vlog.state_dir(), "last_state.json")

EFFECT_IDS = {"effect-none": "none", "effect-cycle": "cycle", "effect-fade": "fade"}
MODE_IDS = ("effect-none", "effect-cycle", "effect-fade")
MODE_NAMES = {
    "effect-none": t("tui.mode_static"),
    "effect-cycle": t("tui.mode_cycle"),
    "effect-fade": t("tui.mode_fade"),
}

NAME_WIDTH = 10
LABEL_WIDTH = NAME_WIDTH + 4


class RowButton(Button):
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
    gap = "" if mode_id == MODE_IDS[-1] else "  "
    return f"[{mark}] {MODE_NAMES[mode_id]}{gap}"


def preset_label(name: str, rgb) -> Text:
    text = Text(f"{name:<{NAME_WIDTH}.{NAME_WIDTH}} ")
    text.append("[", style="dim")
    text.append("■", style=f"bold {pal.to_hex(rgb)}")
    text.append("]", style="dim")
    return text


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(data):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        vlog.log("warn", TOOL, f"state save failed: {e}")


def is_dry():
    return os.environ.get("VICTUS_DRY_RUN") == "1"


async def run_backend(args):
    """victus-kbd (sudo -n при необходимости) — без блокировки интерфейса."""
    cmd = [BACKEND] + [str(a) for a in args]
    if not is_dry() and os.geteuid() != 0:
        cmd = ["sudo", "-n"] + cmd
    vlog.log_info(TOOL, f"backend {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        out, err = await proc.communicate()
    except OSError as e:
        vlog.log_error(TOOL, f"backend spawn failed: {e}", exc=False)
        return 127, "", str(e)
    return proc.returncode, out.decode().strip(), err.decode().strip()


def luminance(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sudo_hint(text):
    low = text.lower()
    if "password" in low or "terminal" in low or "sudo" in low:
        return t("tui.need_sudo")
    return text


class SavePresetScreen(ModalScreen):
    """Диалог имени для [ Save Preset ]."""

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


class KbdTab(Vertical):
    power = reactive(True)
    color = reactive((255, 255, 255))
    effect = reactive("none")
    speed = reactive(1.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        state = load_state()
        rgb = state.get("rgb")
        if (
            isinstance(rgb, list)
            and len(rgb) == 3
            and all(isinstance(v, int) and 0 <= v <= 255 for v in rgb)
        ):
            self.color = tuple(rgb)
        self.power = bool(state.get("power", True))
        if state.get("effect") in ("none", "cycle", "fade"):
            self.effect = state["effect"]
        try:
            self.speed = min(5.0, max(0.2, float(state.get("speed", 1.0))))
        except (TypeError, ValueError):
            self.speed = 1.0
        self._sync_target = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield from self._presets_panel()
            yield from self._color_panel()
            yield from self._effects_panel()
        with Horizontal(id="statusline"):
            with Horizontal(id="status-flow"):
                yield Static("", id="color-tag")
                yield Static("", id="status")
            yield Switch(value=self.power, id="power")

    def _presets_panel(self):
        panel = Vertical(classes="panel", id="presets-panel")
        panel.border_title = t("tui.sec_presets")
        with panel:
            yield ScrollableContainer(id="preset-list")

    def _color_panel(self):
        panel = Vertical(classes="panel", id="color-panel")
        panel.border_title = t("tui.sec_picker")
        with panel:
            with Horizontal(id="picker-top"):
                with Vertical(id="hsv-column"):
                    yield from self._hsv_row("hue", t("tui.lab_hue"), 0, 360)
                    yield from self._hsv_row("sat", t("tui.lab_sat"), 0, 100)
                    yield from self._hsv_row("val", t("tui.lab_val"), 0, 100)
                with Vertical(id="preview-column"):
                    yield Static("", id="preview")
                    with Vertical(id="readouts"):
                        yield Static("H: 0", id="read-h", classes="readout")
                        yield Static("S: 0", id="read-s", classes="readout")
                        yield Static("V: 0", id="read-v", classes="readout")
                        yield Static("Hex: [#000000]", id="read-hex", classes="readout")
            with Horizontal(id="picker-actions"):
                yield Button(Text(t("tui.btn_apply")), id="apply")
                yield Button(Text(t("tui.btn_copy_hex")), id="copy-hex")
                yield Button(Text(t("tui.btn_save_preset")), id="save-name")

    def _hsv_row(self, sid, label, lo, hi):
        with Horizontal(classes="hsv-row", id=f"row-{sid}"):
            yield Label(label, classes="hsv-label")
            yield AsciiSlider(min=lo, max=hi, step=1, value=lo, id=sid)
            yield Static(f"{lo}", id=f"{sid}-val", classes="hsv-value")

    def _effects_panel(self):
        panel = Vertical(classes="panel", id="effects-panel")
        panel.border_title = t("tui.sec_effects")
        with panel:
            with Horizontal(id="effect-modes"):
                for mid in MODE_IDS:
                    active = EFFECT_IDS[mid] == self.effect
                    yield RowButton(
                        Text(mode_label(mid, active)),
                        id=mid,
                        classes=f"mode{' on' if active else ''}",
                    )
            creator = Vertical(id="creator")
            creator.border_title = t("tui.sec_creator")
            with creator:
                yield SineWave(speed=self.speed, id="sine")
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

    def on_mount(self):
        table = pal.all_colors()
        listing = self.query_one("#preset-list", ScrollableContainer)
        selected = None
        for name in sorted(table):
            rgb = table[name]
            btn = RowButton(preset_label(name, rgb), id=f"c-{name}", classes="preset")
            listing.mount(btn)
            if rgb == self.color and selected is None:
                selected = name
        self._mark_selected(selected)
        self._sync_controls()

    def _mark_selected(self, name):
        for btn in self.query(".preset"):
            btn.set_class(name is not None and btn.id == f"c-{name}", "selected")

    def _sync_controls(self):
        original = self.color
        h, s, v = pal.rgb_to_hsv(original)
        target = (round(h), round(s * 100), round(v * 100))
        self._sync_target = target
        self.query_one("#hue", AsciiSlider).set_value(target[0])
        self.query_one("#sat", AsciiSlider).set_value(target[1])
        self.query_one("#val", AsciiSlider).set_value(target[2])
        self.query_one("#hue-val", Static).update(f"{target[0]}")
        self.query_one("#sat-val", Static).update(f"{target[1]}")
        self.query_one("#val-val", Static).update(f"{target[2]}")
        self.color = original
        self._refresh_readout()

    def _refresh_readout(self):
        rgb = self.color
        hexv = pal.to_hex(rgb)
        h, s, v = pal.rgb_to_hsv(rgb)
        self.query_one("#preview").styles.background = hexv
        self.query_one("#read-h", Static).update(f"H: {round(h)}")
        self.query_one("#read-s", Static).update(f"S: {round(s * 100)}")
        self.query_one("#read-v", Static).update(f"V: {round(v * 100)}")
        self.query_one("#read-hex", Static).update(Text(f"Hex: [{hexv}]"))
        self.query_one("#color-tag", Static).update(t("tui.color_tag", hex=hexv))

    def _set_status(self, text, error=False):
        st = self.query_one("#status", Static)
        st.update(Text(text))
        st.styles.color = "#ff6b6b" if error else "#7ee787"

    def _store(self):
        save_state(
            {
                "rgb": list(self.color),
                "hex": pal.to_hex(self.color),
                "power": self.power,
                "effect": self.effect,
                "speed": self.speed,
                "updated": datetime.datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
            }
        )

    def _from_hsv_controls(self):
        hue = self.query_one("#hue", AsciiSlider).value
        sat = self.query_one("#sat", AsciiSlider).value
        val = self.query_one("#val", AsciiSlider).value
        h, s, v = hue, sat / 100.0, val / 100.0
        if self._sync_target == (hue, sat, val):
            return
        self._sync_target = None
        self.query_one("#hue-val", Static).update(f"{hue:.0f}")
        self.query_one("#sat-val", Static).update(f"{sat:.0f}")
        self.query_one("#val-val", Static).update(f"{val:.0f}")
        self.color = pal.hsv_to_rgb(h, s, v)
        self._refresh_readout()

    async def _apply_current(self):
        r, g, b = self.color if self.power else (0, 0, 0)
        rc, out, err = await run_backend([r, g, b])
        if rc != 0:
            msg = _sudo_hint(err or out) or t("tui.apply_failed", rc=rc)
            self._set_status(msg, error=True)
            vlog.log_error(TOOL, f"apply rc={rc} err={err or out}", exc=False)
            return
        self._set_status(t("tui.applied", color=pal.to_hex((r, g, b))))
        self._store()

    async def _select_preset(self, name):
        rgb = pal.all_colors().get(name)
        if rgb is None:
            return
        self.color = rgb
        self.power = True
        self.query_one("#power", Switch).value = True
        self._mark_selected(name)
        self._sync_controls()
        await self._apply_current()

    def _cycle_colors(self):
        base = pal.rgb_to_hsv(self.color)[0]
        return [
            pal.hsv_to_rgb(base, 1.0, 1.0),
            pal.hsv_to_rgb(base + 120, 1.0, 1.0),
            pal.hsv_to_rgb(base + 240, 1.0, 1.0),
        ]

    async def _start_effect(self):
        if self.effect == "fade":
            self._set_status(t("tui.fade_unsupported"), error=True)
            return
        if self.effect != "cycle":
            self._set_status(t("tui.effect_none_status"))
            return
        colors = self._cycle_colors()
        args = ["cycle"]
        args += [",".join(str(c) for c in rgb) for rgb in colors]
        args += ["--delay", f"{self.speed:.1f}", "--bg"]
        rc, out, err = await run_backend(args)
        if rc != 0:
            self._set_status(
                _sudo_hint(err or out) or t("tui.effect_failed", rc=rc), error=True
            )
            vlog.log_error(TOOL, f"effect rc={rc} err={err or out}", exc=False)
            return
        self._set_status(out or t("tui.effect_started"))
        self._store()

    async def _stop_effect(self):
        rc, out, err = await run_backend(["stop"])
        self._set_status(out or err or t("tui.effect_stopped"))
        self._store()

    def on_switch_changed(self, event):
        if event.switch.id != "power":
            return
        self.power = bool(event.value)
        self.run_worker(self._apply_current(), exclusive=True)

    @on(AsciiSlider.Changed)
    def slider_changed(self, event):
        sid = event.slider.id
        if sid == "speed":
            self.speed = round(event.value, 1)
            self.query_one("#speed-label", Static).update(
                f"{t('tui.speed_label')} {self.speed:.1f}"
            )
            self.query_one("#sine", SineWave).speed = self.speed
            return
        if sid in ("hue", "sat", "val"):
            self._from_hsv_controls()

    def _set_effect(self, mode_id):
        if mode_id not in EFFECT_IDS:
            return
        self.effect = EFFECT_IDS[mode_id]
        for mid in MODE_IDS:
            btn = self.query_one(f"#{mid}", Button)
            active = mid == mode_id
            btn.label = Content.from_text(Text(mode_label(mid, active)))
            btn.set_class(active, "on")

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
            hexv = pal.to_hex(self.color)
            try:
                self.app.copy_to_clipboard(hexv)
                self._set_status(t("tui.copied", hex=hexv))
            except Exception as e:
                vlog.log("warn", TOOL, f"clipboard failed: {e}")
                self._set_status(hexv)
        elif bid == "save-name":
            self._prompt_save()

    @work(exclusive=True)
    async def _prompt_save(self):
        result = await self.app.push_screen(
            SavePresetScreen(pal.to_hex(self.color)), wait_for_dismiss=True
        )
        if result:
            await self._save_named_color(str(result))

    async def _save_named_color(self, name):
        if not pal.NAME_RE.match(name):
            self._set_status(t("cm.name_rule"), error=True)
            return
        proc = await asyncio.create_subprocess_exec(
            COLORMAKER,
            "add",
            name,
            pal.to_hex(self.color),
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
