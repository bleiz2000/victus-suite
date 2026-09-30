"""Вкладка «vertil» — мониторинг и управление вентиляторами HP Victus.

Слева  ТЕЛЕМЕТРИЯ    — CPU / GPU / VRM* (ACPI-прокси), обороты правого и
                       левого вентилятора, duty PWM, режим hwmon.
В центре УПРАВЛЕНИЕ  — режимы [Manual | SMART | BIOS Auto] и два слайдера
                       PWM 0..255 (~RPM): правый = CPU (pwm1/fan1),
                       левый = GPU (pwm2/fan2).
Справа  БЕЗОПАСНОСТЬ — пороги guard/smart/авария из presets.json + доступ.

Чтение — fanlib.Sensors (без root), запись — fanctl подкомандой
`sudo -n bin/victus-kbd fans …` (NOPASSWD-правило подсветки, без пароля).
Автопилот — fanlib.Smart, шаг 1 с, тот же контроллер, что в fanpult/phase.py.
Вход в MANUAL безопасен (драйвер снапшотит RPM); выход в BIOS AUTO требует
повторного клика за 30 с — переход глушит вентиляторы на ~215 с.
"""

from __future__ import annotations

import asyncio
import time

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.widgets import Button, Label, Static

from tui import vertil_core
from tui.kbd_tab import RowButton
from tui.slider import AsciiSlider

import victus_log as vlog
from i18n import t

TOOL = "vertil"

MODE_ORDER = ("manual", "smart", "auto")
MODE_IDS = {"manual": "v-mode-manual", "smart": "v-mode-smart", "auto": "v-mode-auto"}
SLIDER_IDS = ("v-pwm-cpu", "v-pwm-gpu")
AUTO_CONFIRM_S = 30.0
FAIL_STOP = 10


def mode_name(kind: str) -> str:
    return {
        "manual": t("tui.vertil_mode_manual"),
        "smart": t("tui.vertil_mode_smart"),
        "auto": t("tui.vertil_mode_auto"),
    }.get(kind, kind)


def mode_label(kind: str, active: bool) -> str:
    return "[%s] %s" % ("*" if active else " ", mode_name(kind))


def temp_style(value, warn: float = 85.0, hot: float = 95.0) -> str:
    if value is None:
        return "dim"
    if value >= hot:
        return "bold red"
    if value >= warn:
        return "yellow"
    return "green"


def fmt_t(value) -> str:
    return "-" if value is None else "%.1f °C" % value


def fmt_rpm(value) -> str:
    return "-" if value is None else "%d RPM" % int(value)


def fmt_w(value) -> str:
    return "-" if value is None else "%.0f W" % value


def fmt_c(value) -> str:
    """Порог температуры коротко: 93.0 -> 93 (строка должна влезать в панель)."""
    if value is None or value == "-":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return "%d" % number
    return "%.1f" % number


def est_rpm(pwm) -> str:
    """~RPM для заданного PWM: линейная оценка от max_rpm пресета."""
    if pwm is None:
        return "-"
    return "%d" % round(pwm / 255.0 * vertil_core.max_rpm())


def line(*cells) -> Text:
    """Строка из (текст, стиль) пар."""
    text = Text()
    for content, style in cells:
        text.append(str(content), style=style or "")
    return text


class VertilTab(Vertical):
    autopilot = reactive(False)
    _rebuilding = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.autopilot = bool(vertil_core.session["autopilot"])
        self._smart = None
        self._snap = None
        self._access = None
        self._mode = None
        self._target = [None, None]
        self._setpoint = [None, None]
        self._auto_armed = 0.0
        self._syncing = False
        self._pwm_timer = None
        self._poll = None
        self._last_step = time.monotonic()
        self._fail_count = 0
        self._emerg_shown = None
        self._want_restore = False

    # --- композиция ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="vbody"):
            yield from self._telemetry_panel()
            yield from self._control_panel()
            yield from self._limits_panel()
        with Horizontal(id="vstatusline"):
            with Horizontal(id="vstatus-flow"):
                yield Static("", id="vstatus-tag")
                yield Static("", id="vstatus")

    def _telemetry_panel(self):
        panel = Vertical(classes="panel", id="vtelemetry")
        panel.border_title = t("tui.sec_telemetry")
        with panel:
            yield Static("", id="v-temps", classes="vblock")
            yield Static("", id="v-fans", classes="vblock")
            yield Static("", id="v-mode-info", classes="vblock")
        return []

    def _control_panel(self):
        panel = Vertical(classes="panel", id="vcontrol")
        panel.border_title = t("tui.sec_control")
        with panel:
            block = Vertical(id="v-mode-block")
            with block:
                for kind in MODE_ORDER:
                    yield RowButton(
                        Text(mode_label(kind, False)),
                        id=MODE_IDS[kind],
                        classes=f"mode{' on' if kind == 'manual' else ''}",
                    )
            with Horizontal(classes="vrow", id="v-row-cpu"):
                # панель УПРАВЛЕНИЕ всегда по-английски (пожелание пользователя),
                # телеметрия остаётся на языке интерфейса
                yield Label("Right fan", classes="vlabel")
                yield AsciiSlider(min=0, max=255, step=1, value=0, id="v-pwm-cpu")
                yield Static("-", id="v-pwm-cpu-val", classes="vvalue")
            with Horizontal(classes="vrow", id="v-row-gpu"):
                yield Label("Left fan", classes="vlabel")
                yield AsciiSlider(min=0, max=255, step=1, value=0, id="v-pwm-gpu")
                yield Static("-", id="v-pwm-gpu-val", classes="vvalue")
        return []

    def _limits_panel(self):
        panel = Vertical(classes="panel", id="vlimits")
        panel.border_title = t("tui.sec_limits")
        with panel:
            yield Static("", id="v-limits", classes="vblock")
        return []

    # --- старт --------------------------------------------------------------

    def on_mount(self):
        self._render_limits()
        self._sync_mode_buttons()
        # _boot/_tick уже @work — декоратор сам стартует воркер
        self._boot()
        self._poll = self.set_interval(1.0, self._tick)

    @work(exclusive=True, group="vertil-boot")
    async def _boot(self):
        self._access = await asyncio.to_thread(vertil_core.probe_access)
        self._render_limits()
        if self._access in ("direct", "sudo"):
            self._set_status(t("tui.vertil_ready"))
            # режим железа читаем из первого снапшота (_tick), не здесь:
            # один снапшот вместо двух и честная картина на старте
            self._want_restore = True
        elif self._access == "need-password":
            self._set_status(t("tui.vertil_need_sudo"), error=True)
        elif self._access in ("no-hwmon", "no-vertil"):
            self._set_status(t("tui.vertil_no_hwmon"), error=True)
        else:
            self._set_status(t("tui.vertil_access_error"), error=True)

    @work(exclusive=True, group="vertil-tick")
    async def _tick(self):
        # до восстановления режима читаем железо даже со скрытой вкладки
        if not self.display and not self.autopilot and not self._want_restore:
            return
        snap = await asyncio.to_thread(vertil_core.snapshot)
        if snap is None:
            if self.display:
                self._set_status(t("tui.vertil_read_failed"), error=True)
            return
        self._snap = snap
        if self._want_restore:
            self._want_restore = False
            await self._restore_mode(snap)
        if self.autopilot:
            await self._smart_step(snap)
        self._paint(snap)

    async def _restore_mode(self, snap: dict):
        """Старт режима при открытии: первый запуск — SMART, дальше — свой выбор.

        Выбор человека (Manual / SMART / AUTO) не сбрасывается: он лежит в
        state/fan_mode.json, режим железа читается из снапшота честно.
        """
        choice = vertil_core.fan_mode_load()
        hw = snap.get("mode_name")
        if choice in (None, "smart"):
            if self.autopilot:
                return
            ok = await self._start_autopilot(
                snap, status=t("tui.vertil_smart_autostart"))
            if ok and choice is None:
                vertil_core.fan_mode_save("smart")
            return
        if choice == "manual":
            if hw != "manual":
                ok, msg = await vertil_core.call("set-mode", "1")
                if not ok:
                    self._note_access(msg)
                    self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
                    return
                vertil_core.session["controlled"] = True
            self._mode = "manual"
            self._setpoint = [snap.get("pwm1"), snap.get("pwm2")]
            self._target = list(self._setpoint)
            self._set_sliders_enabled(True)
            self._sync_mode_buttons()
            self._set_status(t("tui.vertil_manual_on"))
            return
        # choice == "auto": уже в AUTO — только показываем, иначе пишем
        # (переход глушит вентиляторы, но это режим, который выбрали сами)
        if hw != "auto":
            ok, msg = await vertil_core.call("set-mode", "2")
            if not ok:
                self._note_access(msg)
                self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
                return
            vertil_core.session["controlled"] = True
        self._mode = "auto"
        self._setpoint = [None, None]
        self._target = [None, None]
        self._set_sliders_enabled(True)
        self._sync_mode_buttons()
        self._set_status(t("tui.vertil_auto_done"))

    # --- автопилот ----------------------------------------------------------

    async def _smart_step(self, snap: dict):
        now = time.monotonic()
        dt = max(0.0, now - self._last_step)
        self._last_step = now
        if self._smart is None:
            self._smart = vertil_core.make_smart(
                seed=(snap.get("pwm1") or 79, snap.get("pwm2") or 92)
            )
        if self._smart is None:
            await self._stop_autopilot(status=t("tui.vertil_no_hwmon"), error=True)
            return
        p1, p2, action, changed = self._smart.update(snap, dt)
        if not changed:
            return
        ok, msg = await vertil_core.call("set-pwm", str(p1), str(p2))
        if not ok:
            self._fail_count += 1
            self._note_access(msg)
            self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
            if self._fail_count >= FAIL_STOP:
                await self._stop_autopilot(
                    status=t("tui.vertil_stopped"), error=True
                )
            return
        self._fail_count = 0
        vertil_core.session["controlled"] = True
        self._setpoint = [p1, p2]
        self._target = [p1, p2]
        self._set_status(action)

    async def _start_autopilot(self, snap: dict | None = None,
                               status: str | None = None) -> bool:
        ok, msg = await vertil_core.call("set-mode", "1")
        if not ok:
            self._note_access(msg)
            self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
            return False
        vertil_core.session["controlled"] = True
        vertil_core.session["autopilot"] = True
        self._smart = None
        self._fail_count = 0
        self._last_step = time.monotonic()
        if snap is not None:
            self._setpoint = [snap.get("pwm1"), snap.get("pwm2")]
            self._target = list(self._setpoint)
        self._mode = "manual"
        self.autopilot = True
        self._set_sliders_enabled(False)
        self._sync_mode_buttons()
        self._set_status(status or t("tui.vertil_smart_on"))
        return True

    async def _stop_autopilot(self, status: str | None = None, error: bool = False):
        self.autopilot = False
        self._smart = None
        vertil_core.session["autopilot"] = False
        self._fail_count = 0
        self._set_sliders_enabled(True)
        self._sync_mode_buttons()
        if status:
            self._set_status(status, error=error)

    # --- режимы -------------------------------------------------------------

    async def _select_mode(self, kind: str):
        if kind == "auto":
            await self._to_auto()
        elif kind == "manual":
            await self._to_manual()
        elif kind == "smart":
            await self._to_smart()

    async def _to_manual(self):
        self._auto_armed = 0.0
        if self.autopilot:
            await self._stop_autopilot()
        vertil_core.fan_mode_save("manual")
        # железо уже в manual — писать нечего, и не нужен sudo
        if (self._snap or {}).get("mode_name") == "manual":
            self._mode = "manual"
            self._sync_mode_buttons()
            self._set_status(t("tui.vertil_manual_on"))
            return
        ok, msg = await vertil_core.call("set-mode", "1")
        if not ok:
            self._note_access(msg)
            self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
            return
        vertil_core.session["controlled"] = True
        self._mode = "manual"
        self._sync_mode_buttons()
        self._set_status(t("tui.vertil_manual_on"))

    async def _to_smart(self):
        self._auto_armed = 0.0
        if self.autopilot:
            await self._stop_autopilot(status=t("tui.vertil_smart_off"))
            vertil_core.fan_mode_save("manual")
            return
        ok = await self._start_autopilot(self._snap)
        if ok:
            vertil_core.fan_mode_save("smart")

    async def _to_auto(self):
        now = time.monotonic()
        if abs(now - self._auto_armed) > AUTO_CONFIRM_S:
            self._auto_armed = now
            self._set_status(t("tui.vertil_auto_warn"), error=True)
            return
        self._auto_armed = 0.0
        if self.autopilot:
            await self._stop_autopilot()
        ok, msg = await vertil_core.call("set-mode", "2")
        if not ok:
            self._note_access(msg)
            self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
            return
        vertil_core.fan_mode_save("auto")
        self._mode = "auto"
        self._setpoint = [None, None]
        self._sync_mode_buttons()
        self._set_status(t("tui.vertil_auto_done"))

    # --- ручной PWM ---------------------------------------------------------

    async def _apply_pwm(self, p1: int, p2: int):
        if self.autopilot:
            return
        ok, msg = await vertil_core.call("set-pwm", str(p1), str(p2))
        if not ok:
            self._note_access(msg)
            self._set_status(t("tui.vertil_write_failed", msg=msg), error=True)
            return
        vertil_core.session["controlled"] = True
        vertil_core.fan_mode_save("manual")
        # set_pwm сам заходит в MANUAL — индикатор режима обновляем сразу
        self._mode = "manual"
        self._setpoint = [p1, p2]
        self._target = [p1, p2]
        self._sync_mode_buttons()
        self._set_status(
            t("tui.vertil_pwm_set",
              p1=p1, p2=p2, r1=est_rpm(p1), r2=est_rpm(p2))
        )

    # --- отрисовка ----------------------------------------------------------

    def _set_status(self, text, error=False):
        widget = self.query_one("#vstatus", Static)
        widget.update(Text(str(text)))
        widget.styles.color = "#ff6b6b" if error else "#7ee787"

    def _note_access(self, msg: str):
        low = (msg or "").lower()
        if "password" in low or "пароль" in low:
            self._access = "need-password"
            self._render_limits()

    def _paint(self, snap: dict):
        # первый снапшот: показываем реальный режим железа, не догадку
        if self._mode is None:
            self._mode = {"manual": "manual", "auto": "auto"}.get(
                (snap or {}).get("mode_name"))
        self.query_one("#v-temps", Static).update(self._temps_text(snap))
        self.query_one("#v-fans", Static).update(self._fans_text(snap))
        self.query_one("#v-mode-info", Static).update(self._mode_text(snap))
        tag_text, tag_color = self._tag_text(snap)
        tag = self.query_one("#vstatus-tag", Static)
        tag.update(tag_text)
        tag.styles.color = tag_color
        self._render_emergency(snap)
        self._sync_mode_buttons()
        self._sync_sliders(snap)

    def _temps_text(self, snap: dict) -> Text:
        out = Text()
        out.append_text(line(
            ("CPU  ", "dim"), (fmt_t(snap.get("t_cpu")), temp_style(snap.get("t_cpu"))),
            ("  max ", "dim"), (fmt_t(snap.get("t_cpu_max")), temp_style(snap.get("t_cpu_max"))),
        ))
        # RAPL есть не везде — пустую колонку не рисуем
        if snap.get("cpu_w") is not None:
            out.append_text(line(("  ", ""), (fmt_w(snap.get("cpu_w")), "cyan")))
        out.append("\n")
        out.append_text(line(
            ("GPU  ", "dim"), (fmt_t(snap.get("t_gpu")), temp_style(snap.get("t_gpu"))),
            ("  ", ""),
            ("-" if snap.get("gpu_util") is None else "%d %%" % snap["gpu_util"], "dim"),
            ("  ", ""), (fmt_w(snap.get("gpu_w")), "cyan"),
        ))
        out.append("\n")
        out.append_text(line(
            ("VRM* ", "dim"), (fmt_t(snap.get("t_vrm")), temp_style(snap.get("t_vrm"))),
            ("  ", ""), (t("tui.vertil_board"), "dim"),
            (" ", ""), (fmt_t(snap.get("t_board")), temp_style(snap.get("t_board"), 75, 85)),
        ))
        return out

    def _fans_text(self, snap: dict) -> Text:
        out = Text()
        for label, rpm_key, pwm_key in (
            (t("tui.vertil_fan_right"), "fan1", "pwm1"),
            (t("tui.vertil_fan_left"), "fan2", "pwm2"),
        ):
            pwm = snap.get(pwm_key)
            duty = "-" if pwm is None else "%d %%" % round(pwm / 255.0 * 100)
            rpm = snap.get(rpm_key)
            out.append_text(line(
                (label, "dim"), (" ", ""),
                (fmt_rpm(rpm).rjust(9), "green" if (pwm or 0) < 250 else "yellow"),
                ("  PWM ", "dim"), (str(pwm) if pwm is not None else "-", "bold"),
                (" ", ""), (duty.rjust(4), "cyan"),
            ))
            out.append("\n")
        out.append_text(line(
            (t("tui.vertil_target").ljust(6), "dim"),
            ("%s/%s" % (self._setpoint[0] if self._setpoint[0] is not None else "-",
                        self._setpoint[1] if self._setpoint[1] is not None else "-"),
             "bold cyan"),
        ))
        return out

    def _mode_text(self, snap: dict) -> Text:
        mode = snap.get("mode_name") or "-"
        color = {"auto": "green", "manual": "yellow", "max": "red"}.get(mode, "dim")
        ctrl = mode_name("smart") if self.autopilot else (
            mode_name("manual") if mode == "manual" else mode.upper())
        out = Text()
        out.append_text(line(
            ("MODE ", "dim"), (mode, color),
            ("   ", ""), (ctrl, "bold cyan" if self.autopilot else ""),
        ))
        return out

    def _tag_text(self, snap: dict) -> tuple[Text, str]:
        """Компактный чип состояния слева в статус-строке + его цвет."""
        if self._is_emergency(snap):
            text = line(
                ("!! ", "bold red"),
                ("%s/%s °C" % (snap.get("t_cpu") if snap.get("t_cpu") is not None else "-",
                               snap.get("t_gpu") if snap.get("t_gpu") is not None else "-"),
                 "bold red"),
            )
            return text, "#ff6b6b"
        if self.autopilot:
            p1 = self._setpoint[0]
            p2 = self._setpoint[1]
            chip = line(
                ("SMART ▸ ", "bold"),
                ("%s/%s" % (p1 if p1 is not None else "?",
                            p2 if p2 is not None else "?"), ""),
            )
            return chip, "green"
        mode = snap.get("mode_name")
        if mode in ("auto", "max"):
            return Text(mode.upper(), style="green"), "green"
        # hp-wmi не отдаёт setpoint обратно (см. fan-hw-access-report §7) —
        # если мы уже писали, показываем свою команду, а не дрожащий readback
        p1, p2 = self._setpoint
        if p1 is None and p2 is None:
            p1, p2 = snap.get("pwm1"), snap.get("pwm2")
        return line(
            ("PWM ", ""),
            ("%s/%s" % (p1 if p1 is not None else "-",
                        p2 if p2 is not None else "-"), "bold"),
        ), "#7ee787"

    def _is_emergency(self, snap: dict) -> bool:
        emergency = (vertil_core.preset().get("smart") or {}).get("emergency") or {}
        tc, tg = snap.get("t_cpu"), snap.get("t_gpu")
        if tc is not None and tc >= float(emergency.get("cpu_c", 93.0)):
            return True
        if tg is not None and tg >= float(emergency.get("gpu_c", 83.0)):
            return True
        return False

    def _render_emergency(self, snap: dict):
        if not self._is_emergency(snap):
            self._emerg_shown = None
            return
        key = (snap.get("t_cpu"), snap.get("t_gpu"))
        if self._emerg_shown == key:
            return
        self._emerg_shown = key
        self._set_status(
            t("tui.vertil_emergency",
              cpu=snap.get("t_cpu") if snap.get("t_cpu") is not None else "-",
              gpu=snap.get("t_gpu") if snap.get("t_gpu") is not None else "-"),
            error=True,
        )

    def _render_limits(self):
        preset = vertil_core.preset()
        guard, smart = preset.get("guard") or {}, preset.get("smart") or {}
        safety = preset.get("safety") or {}
        emergency = smart.get("emergency") or {}
        verdict = self._access or "probe"
        rows = [
            (t("tui.vertil_l_guard"),
             "CPU %s · GPU %s °C" % (fmt_c(guard.get("cpu_hot_c")),
                                     fmt_c(guard.get("gpu_hot_c")))),
            (t("tui.vertil_l_smart"),
             "%s..%s" % (smart.get("floor_pwm", "-"), smart.get("ceil_pwm", "-"))),
            (t("tui.vertil_l_emerg"),
             "CPU %s · GPU %s °C" % (fmt_c(emergency.get("cpu_c")),
                                     fmt_c(emergency.get("gpu_c")))),
            (t("tui.vertil_l_hold"),
             "%s PWM" % safety.get("hold_pwm_on_controller_loss", vertil_core.hold_pwm())),
            (t("tui.vertil_l_preset"), preset.get("name", "-")),
            (t("tui.vertil_l_access"), t("tui.vertil_acc_%s" % verdict)),
        ]
        out = Text()
        good = verdict in ("direct", "sudo")
        for index, (label, value) in enumerate(rows):
            if index:
                out.append("\n")
            style = "cyan" if index < 5 else ("green" if good else "red")
            out.append_text(line((label.ljust(8), "dim"), (value, style)))
        self.query_one("#v-limits", Static).update(out)

    def _sync_mode_buttons(self):
        mode = self._mode
        active = "smart" if self.autopilot else (
            "manual" if mode == "manual" else "auto" if mode == "auto" else None)
        for kind in MODE_ORDER:
            button = self.query_one("#%s" % MODE_IDS[kind], Button)
            button.label = Content.from_text(Text(mode_label(kind, kind == active)))
            button.set_class(kind == active, "on")

    def _sync_sliders(self, snap: dict):
        if self._syncing:
            return
        if self.autopilot or self._mode == "manual":
            target = self._target
        else:
            target = [snap.get("pwm1"), snap.get("pwm2")]
        if target[0] is None and target[1] is None:
            target = [snap.get("pwm1"), snap.get("pwm2")]
        self._syncing = True
        try:
            for sid, value in zip(SLIDER_IDS, target):
                if value is None:
                    continue
                slider = self.query_one("#%s" % sid, AsciiSlider)
                slider.set_value(value)
                self._set_val_label(sid, int(value))
        finally:
            self._syncing = False

    def _set_val_label(self, sid: str, value: int):
        self.query_one("#%s-val" % sid, Static).update(
            "%d ~%s RPM" % (value, est_rpm(value))
        )

    def _set_sliders_enabled(self, enabled: bool):
        for sid in SLIDER_IDS:
            self.query_one("#%s" % sid, AsciiSlider).disabled = not enabled

    # --- события ------------------------------------------------------------

    @on(AsciiSlider.Changed)
    def slider_changed(self, event):
        if event.slider.id not in SLIDER_IDS:
            return
        if self._syncing or self.autopilot:
            return
        p1 = int(self.query_one("#v-pwm-cpu", AsciiSlider).value)
        p2 = int(self.query_one("#v-pwm-gpu", AsciiSlider).value)
        self._target = [p1, p2]
        self._set_val_label("v-pwm-cpu", p1)
        self._set_val_label("v-pwm-gpu", p2)
        if self._pwm_timer is not None:
            self._pwm_timer.stop()
        self._pwm_timer = self.set_timer(
            0.4, lambda: self.run_worker(self._apply_pwm(p1, p2), exclusive=True,
                                         group="vertil-write")
        )

    @on(Button.Pressed)
    def button_pressed(self, event):
        for kind, bid in MODE_IDS.items():
            if event.button.id == bid:
                self.run_worker(self._select_mode(kind), exclusive=False)
                return

    def on_unmount(self):
        if self._pwm_timer is not None:
            self._pwm_timer.stop()
            self._pwm_timer = None
        timer = self._poll
        if timer is not None:
            timer.stop()
            self._poll = None
        # пересборка под смену языка: автопилот и железо не трогаем
        if VertilTab._rebuilding:
            return
        msg = vertil_core.shutdown()
        if msg:
            vlog.log_info(TOOL, f"window closed — {msg}")
