"""ASCII-виджеты TUI: AsciiSlider (прогресс-бар) и SineWave (синусоида).

В Textual 8.2.8 нет виджета Slider, поэтому ползунок рисуем сами.

AsciiSlider  `[======== ]`  — клик/драг мышью, колесо, ← →, Home/End.
             ALLOW_SELECT=False: клик двигает ползунок, а не выделяет текст.

SineWave     сглаженная синусоида (9 подуровней высоты внутри ячейки),
             живая анимация, скорость = Effect Speed.
"""

import math

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

RAMP = ("▔", "▇", "▆", "▅", "▄", "▃", "▂", "▁")


class AsciiSlider(Widget):
    """Полоса `[==== ]`: значение 0..max, ширина = доступное место."""

    class Changed(Message):
        def __init__(self, slider: "AsciiSlider", value: float) -> None:
            super().__init__()
            self.slider = slider
            self.value = value

        @property
        def id(self):
            return self.slider.id

    can_focus = True
    ALLOW_SELECT = False
    min = 0.0
    max = 1.0
    step = 1.0
    value = reactive(0.0, recompose=False)
    unit = ""

    def __init__(
        self,
        min: float = 0.0,
        max: float = 1.0,
        step: float = 1.0,
        value: float = 0.0,
        unit: str = "",
        *,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.min = float(min)
        self.max = float(max)
        self.step = float(step) or 1.0
        self.unit = unit
        self._drag = False
        self.value = self._clamp(self._quantize(value))

    def _quantize(self, v: float) -> float:
        steps = round((v - self.min) / self.step)
        return self.min + steps * self.step

    def _clamp(self, v: float) -> float:
        return max(self.min, min(self.max, v))

    def set_value(self, v: float, notify: bool = False):
        new = self._clamp(self._quantize(float(v)))
        if new == self.value:
            return
        self.value = new
        self.refresh()
        if notify:
            self.post_message(self.Changed(self, new))

    @property
    def fraction(self) -> float:
        span = self.max - self.min
        return 0.0 if span <= 0 else (self.value - self.min) / span

    def render(self) -> Text:
        width = max(self.size.width, 3)
        inner = max(width - 2, 1)
        filled = max(0, min(inner, round(self.fraction * inner)))
        text = Text()
        text.append("[", style="dim")
        text.append("=" * filled, style="bold")
        text.append(" " * (inner - filled))
        text.append("]", style="dim")
        return text

    def _set_from_x(self, x: int):
        if self.max <= self.min:
            return
        width = max(self.size.width, 3)
        frac = max(0, min(x, width - 1)) / max(1, width - 1)
        self.set_value(self.min + frac * (self.max - self.min), notify=True)

    def on_mouse_down(self, event: events.MouseDown):
        if self.max <= self.min:
            return
        self._drag = True
        self.capture_mouse(True)
        self._set_from_x(event.x)
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove):
        if not self._drag:
            return
        self._set_from_x(event.x)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        if not self._drag:
            return
        self._drag = False
        self.capture_mouse(False)
        event.stop()

    def on_key(self, event: events.Key):
        key = event.key
        if key in ("left", "down"):
            self.set_value(self.value - self.step, notify=True)
        elif key in ("right", "up"):
            self.set_value(self.value + self.step, notify=True)
        elif key == "home":
            self.set_value(self.min, notify=True)
        elif key == "end":
            self.set_value(self.max, notify=True)
        elif key == "pageup":
            self.set_value(self.value + self.step * 10, notify=True)
        elif key == "pagedown":
            self.set_value(self.value - self.step * 10, notify=True)
        else:
            return
        event.stop()
        event.prevent_default()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp):
        self.set_value(self.value + self.step, notify=True)
        event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        self.set_value(self.value - self.step, notify=True)
        event.stop()

    def watch_value(self, value: float):
        self.refresh()


MiniSlider = AsciiSlider


class SineWave(Widget):
    """Живая синусоида: каждый столбец — блочный глиф своего подуровня."""

    period = reactive(0.0)
    speed = reactive(1.0)
    phase = reactive(0.0)

    def __init__(
        self,
        period: float = 0.0,
        speed: float = 1.0,
        *,
        animate: bool = True,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.period = float(period)
        self.speed = float(speed)
        self._animate = animate
        self._timer = None

    def on_mount(self):
        if self._animate:
            self._timer = self.set_interval(0.12, self._tick)

    def _tick(self):
        self.phase = (self.phase + 0.22 * max(self.speed, 0.05)) % (2 * math.pi)

    def render(self) -> Text:
        width = max(self.size.width, 4)
        height = max(self.size.height, 1)
        mid = (height - 1) / 2.0
        amp = max(mid, 0.5) * 0.8
        period = self.period if self.period >= 4.0 else float(width) / 1.5
        rows = [[" "] * width for _ in range(height)]

        def glyph(y: float) -> str:
            row = int(max(0.0, min(height - 1e-6, y)))
            frac = y - row
            return RAMP[max(0, min(7, int(frac * 8)))]

        def put(x: int, y: int, char: str):
            if 0 <= x < width and 0 <= y < height:
                rows[y][x] = char

        prev = None
        for x in range(width):
            y = mid + amp * math.sin((2 * math.pi * x) / period + self.phase)
            y = max(0.0, min(height - 1e-6, y))
            row = int(y)
            if prev is not None and prev != row:
                step = 1 if row > prev else -1
                for between in range(prev, row, step):
                    put(x, between, "│")
            put(x, row, glyph(y))
            prev = row
        text = Text()
        for i, line in enumerate(rows):
            if i:
                text.append("\n")
            text.append("".join(line))
        return text

    def watch_phase(self, phase: float):
        self.refresh()

    def watch_speed(self, speed: float):
        self.refresh()

    def on_unmount(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
