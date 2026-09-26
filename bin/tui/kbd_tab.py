"""Вкладка «Подсветка»: палитра, HSV-слайдеры, вкл/выкл, эффекты.

TUI = обёртка над CLI: запись цвета/эффектов идёт только через victus-kbd,
палитра — через victus_palette (без дублей). Состояние: state/last_state.json.

Дизайн-решение: слайдеры рисуют предпросмотр (свотч/hex), а в EC цвет
уходит только по явному действию — «Применить», клик пресета, Вкл/Выкл,
«Старт» эффекта. Это одна команда = одно действие, как в CLI.
"""

import asyncio
import datetime
import json
import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
    Switch,
)

from tui.slider import MiniSlider

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
        if state.get("effect") in ("none", "cycle"):
            self.effect = state["effect"]
        try:
            self.speed = min(5.0, max(0.2, float(state.get("speed", 1.0))))
        except (TypeError, ValueError):
            self.speed = 1.0
        self._sync_target = None

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="kbd-scroll"):
            yield from self._body()
        yield Static(t("tui.status_ready"), id="status", classes="status")

    def _body(self):
        with Horizontal(classes="row top-row"):
            yield Label(t("tui.power"), classes="row-label")
            yield Switch(value=self.power, id="power")
            yield Static("", id="current-color")

        yield Label(t("tui.presets"), classes="section-title")
        with ScrollableContainer(id="palette-scroll"):
            yield Grid(id="palette")

        yield Label(t("tui.picker"), classes="section-title")
        with Vertical(classes="picker"):
            with Horizontal(classes="slider-row"):
                yield Label(t("tui.hue"), classes="slider-label")
                yield MiniSlider(min=0, max=360, step=1, value=0, unit="°", id="hue")
                yield Static("0°", id="hue-val", classes="slider-value")
            with Horizontal(classes="slider-row"):
                yield Label(t("tui.sat"), classes="slider-label")
                yield MiniSlider(min=0, max=100, step=1, value=100, unit="%", id="sat")
                yield Static("100%", id="sat-val", classes="slider-value")
            with Horizontal(classes="slider-row"):
                yield Label(t("tui.val"), classes="slider-label")
                yield MiniSlider(min=0, max=100, step=1, value=100, unit="%", id="val")
                yield Static("100%", id="val-val", classes="slider-value")

            yield Static("", id="swatch")
            yield Static("", id="color-readout", classes="readout")
            with Horizontal(classes="row"):
                yield Button(t("tui.apply"), id="apply", variant="primary")
                yield Button(t("tui.copy_hex"), id="copy-hex")
                yield Input(placeholder=t("tui.name_placeholder"), id="name-input")
                yield Button(t("tui.save_name"), id="save-name")

        yield Label(t("tui.effects"), classes="section-title")
        with Horizontal(classes="row effects-row"):
            with RadioSet(id="effect"):
                yield RadioButton(
                    t("tui.effect_none"), id="effect-none", value=self.effect == "none"
                )
                yield RadioButton(
                    t("tui.effect_cycle"), id="effect-cycle", value=self.effect == "cycle"
                )
                yield RadioButton(t("tui.effect_fade"), id="effect-fade", disabled=True)
            with Vertical(classes="speed-box"):
                with Horizontal(classes="slider-row"):
                    yield Label(t("tui.speed"), classes="slider-label")
                    yield MiniSlider(
                        min=0.2, max=5.0, step=0.1, value=self.speed, id="speed"
                    )
                    yield Static(f"{self.speed:.1f}", id="speed-val", classes="slider-value")
                with Horizontal(classes="row"):
                    yield Button(t("tui.start"), id="effect-start", variant="success")
                    yield Button(t("tui.stop"), id="effect-stop", variant="error")

    def on_mount(self):
        table = pal.all_colors()
        palette = self.query_one("#palette")
        for name in sorted(table):
            rgb = table[name]
            btn = Button(name, id=f"c-{name}", classes="swatch")
            btn.styles.background = pal.to_hex(rgb)
            btn.styles.color = "#000000" if luminance(rgb) > 0.5 else "#ffffff"
            palette.mount(btn)
        self._sync_controls()
        self._set_status(t("tui.status_ready"))

    def _sync_controls(self):
        original = self.color
        h, s, v = pal.rgb_to_hsv(original)
        target = (round(h), round(s * 100), round(v * 100))
        self._sync_target = target
        self.query_one("#hue", MiniSlider).set_value(target[0])
        self.query_one("#sat", MiniSlider).set_value(target[1])
        self.query_one("#val", MiniSlider).set_value(target[2])
        self.query_one("#hue-val", Static).update(f"{target[0]}°")
        self.query_one("#sat-val", Static).update(f"{target[1]}%")
        self.query_one("#val-val", Static).update(f"{target[2]}%")
        self.color = original
        self._refresh_readout()

    def _refresh_readout(self):
        rgb = self.color
        hexv = pal.to_hex(rgb)
        h, s, v = pal.rgb_to_hsv(rgb)
        self.query_one("#swatch").styles.background = hexv
        self.query_one("#color-readout", Static).update(
            f"rgb{rgb}   {hexv}   hsv({h:.0f}°, {s:.2f}, {v:.2f})"
        )
        self.query_one("#current-color", Static).update(hexv)

    def _set_status(self, text, error=False):
        st = self.query_one("#status", Static)
        st.update(text)
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
        hue = self.query_one("#hue", MiniSlider).value
        sat = self.query_one("#sat", MiniSlider).value
        val = self.query_one("#val", MiniSlider).value
        h, s, v = hue, sat / 100.0, val / 100.0
        if self._sync_target == (h, sat, val):
            return
        self._sync_target = None
        self.query_one("#hue-val", Static).update(f"{h:.0f}°")
        self.query_one("#sat-val", Static).update(f"{s * 100:.0f}%")
        self.query_one("#val-val", Static).update(f"{v * 100:.0f}%")
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
        if self.effect != "cycle":
            self._set_status(t("tui.effect_none_status"))
            return
        colors = self._cycle_colors()
        args = ["cycle"]
        args += [",".join(str(c) for c in rgb) for rgb in colors]
        args += ["--delay", f"{self.speed:.1f}", "--bg"]
        rc, out, err = await run_backend(args)
        if rc != 0:
            self._set_status(_sudo_hint(err or out) or t("tui.effect_failed", rc=rc), error=True)
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

    @on(MiniSlider.Changed)
    def slider_changed(self, event):
        sid = event.slider.id
        if sid == "speed":
            self.speed = round(event.value, 1)
            self.query_one("#speed-val", Static).update(f"{self.speed:.1f}")
            return
        if sid in ("hue", "sat", "val"):
            self._from_hsv_controls()

    def _effect_changed(self, event):
        pressed = event.pressed
        if pressed is None or pressed.id not in EFFECT_IDS:
            return
        self.effect = EFFECT_IDS[pressed.id]

    def on_radioset_changed(self, event):
        self._effect_changed(event)

    def on_radio_set_changed(self, event):
        self._effect_changed(event)

    async def on_button_pressed(self, event):
        bid = event.button.id or ""
        if bid.startswith("c-"):
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
            await self._save_named_color()

    async def _save_named_color(self):
        name = self.query_one("#name-input", Input).value.strip().lower()
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
            self._set_status(err.decode().strip() or t("tui.apply_failed", rc=proc.returncode), error=True)
            return
        self.query_one("#name-input", Input).value = ""
        self._set_status(out.decode().strip() or t("tui.saved"))
        vlog.log_info(TOOL, f"saved color {name}={self.color}")
