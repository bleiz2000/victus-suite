"""MiniSlider — простой слайдер для TUI (в Textual 8.2.8 нет виджета Slider).

Поведение:
  клик мышью по полосе — перейти к позиции;
  колесо мыши / ← → — шаг;
  Home / End — минимум / максимум;
  значение + событие Changed (как у Slider.Changed).

Рендер: `──────●─────────` — маркер на позиции значения.
"""

from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget


class MiniSlider(Widget):
    class Changed(Message):
        def __init__(self, slider: "MiniSlider", value: float) -> None:
            super().__init__()
            self.slider = slider
            self.value = value

        @property
        def id(self):
            return self.slider.id

    can_focus = True
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

    def render(self):
        from rich.text import Text

        width = max(self.size.width, 5)
        span = self.max - self.min
        frac = 0.0 if span <= 0 else (self.value - self.min) / span
        pos = round(frac * (width - 1))
        left = "─" * pos
        right = "─" * (width - 1 - pos)
        text = Text()
        text.append(left, style="dim")
        text.append("●", style="bold cyan")
        text.append(right, style="dim")
        return text

    def _emit(self):
        self.post_message(self.Changed(self, self.value))

    def on_click(self, event: events.Click):
        if self.max <= self.min:
            return
        x = max(0, min(event.x, self.size.width - 1))
        frac = x / max(1, self.size.width - 1)
        self.set_value(self.min + frac * (self.max - self.min), notify=True)
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
