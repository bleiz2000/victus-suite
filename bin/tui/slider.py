"""ASCII-виджеты TUI: AsciiSlider (прогресс-бар) и SineWave (синусоида).

В Textual 8.2.8 нет виджета Slider, поэтому ползунок рисуем сами.

AsciiSlider  `[======== ]`  — клик/драг мышью, колесо, ← →, Home/End.
             ALLOW_SELECT=False: клик двигает ползунок, а не выделяет текст.
             ticks=True — вторая строка с делениями (риски каждые 10% и
             подписи краёв/середины): видно, куда ведёт ползунок.

SineWave     сглаженная синусоида (9 подуровней высоты внутри ячейки),
             живая анимация, скорость = Effect Speed.
"""

import math
import time

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

RAMP = ("▔", "▇", "▆", "▅", "▄", "▃", "▂", "▁")

# Пределы обновления от мыши. Терминал шлёт поток событий (колесо тачпада и
# «пильная» мышь — десятки сообщений за доли секунды); без потолка петля
# сообщений догоняет мышь секундами: полоска «зависает», а потом дёргается
# кусками — то самое «телепортирование».
MOVE_DT = 0.016       # драг: значение меняется не чаще 60 раз в секунду
WHEEL_DT = 0.05       # колесо: накопленные шаги применяются тиками по 50 мс
WHEEL_MAX = 4.0       # сколько шагов колеса успеть за один тик
WHEEL_BACKLOG = 10.0  # потолок «долга» колеса в шагах: лишнее теряется


class AsciiSlider(Widget):
    """Полоса `[==== ]`: значение 0..max, ширина = доступное место.

    ticks=True рисует вторую строку — линейку с делениями каждые 10%
    и подписями min/середина/max; такая полоска занимает 2 строки (CSS).
    """

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
        ticks: bool = False,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.min = float(min)
        self.max = float(max)
        self.step = float(step) or 1.0
        self.unit = unit
        self.ticks = bool(ticks)
        self._drag = False
        self._last_move = 0.0
        self._last_wheel = 0.0
        self._pending_x = None
        self._flush = None
        self._wheel_pending = 0.0
        self._wheel_timer = None
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
        if self.ticks:
            text.append("█" * filled, style="bold")
            text.append("░" * (inner - filled))
        else:
            text.append("=" * filled, style="bold")
            text.append(" " * (inner - filled))
        text.append("]", style="dim")
        if self.ticks:
            text.append("\n")
            text.append("[", style="dim")
            for ch, style in self._ruler_cells(inner):
                text.append(ch, style=style or "")
            text.append("]", style="dim")
        return text

    def _tick_labels(self) -> tuple:
        """Подписи min / середина / максимум для линейки делений."""
        lo, hi = self.min, self.max
        mid = (lo + hi) / 2.0
        if abs(lo - round(lo)) < 1e-9 and abs(hi - round(hi)) < 1e-9:
            return str(int(round(lo))), str(int(round(mid))), str(int(round(hi)))
        return f"{lo:.1f}", f"{mid:.1f}", f"{hi:.1f}"

    def _ruler_cells(self, inner: int) -> list:
        """Строка линейки: риски каждые 10% + подписи min/середина/max.

        Числа пишутся поверх рисок; если ширины не хватает — остаются
        только риски (узкое окно не должно ломать отрисовку).
        """
        cells = [(" ", None)] * max(inner, 0)
        if inner <= 0:
            return cells
        for i in range(11):
            x = round(i * (inner - 1) / 10) if inner > 1 else 0
            cells[x] = ("│", "dim")
        left, mid, right = self._tick_labels()
        if inner < len(left) + len(mid) + len(right) + 2:
            return cells
        for i, ch in enumerate(left):
            cells[i] = (ch, "dim")
        right_start = inner - len(right)
        for i, ch in enumerate(right):
            cells[right_start + i] = (ch, "dim")
        mid_start = (inner - len(mid)) // 2
        if mid_start >= len(left) and mid_start + len(mid) <= right_start:
            for i, ch in enumerate(mid):
                cells[mid_start + i] = (ch, "dim")
        return cells

    def _set_from_x(self, x: int):
        if self.max <= self.min:
            return
        width = max(self.size.width, 3)
        frac = max(0, min(x, width - 1)) / max(1, width - 1)
        self.set_value(self.min + frac * (self.max - self.min), notify=True)

    def on_mouse_down(self, event: events.MouseDown):
        if self.max <= self.min:
            return
        if event.button != 1:  # правая/средняя кнопка — не наш драг
            return
        self._drag = True
        self._last_move = time.monotonic()
        self._pending_x = None
        self._stop_timer("_flush")
        self.capture_mouse(True)
        self._set_from_x(event.x)
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove):
        if not self._drag:
            return
        event.stop()
        now = time.monotonic()
        if now - self._last_move >= MOVE_DT:
            # применяется сразу; всё, что прилетело быстрее, сводится к
            # последней позиции — хвост догонит таймером
            self._stop_timer("_flush")
            self._pending_x = None
            self._last_move = now
            self._set_from_x(event.x)
        else:
            self._pending_x = event.x
            if self._flush is None:
                self._flush = self.set_timer(MOVE_DT, self._flush_move)

    def _flush_move(self):
        """Догнать последнюю позицию мыши после паузы в потоке событий."""
        self._flush = None
        if self._drag and self._pending_x is not None:
            x = self._pending_x
            self._pending_x = None
            self._last_move = time.monotonic()
            self._set_from_x(x)

    def on_mouse_up(self, event: events.MouseUp):
        if not self._drag:
            return
        # хвост событий свёрнут — последняя позиция мыши должна дойти;
        # event.x не берём: некоторые терминалы присылают отпускание с
        # мусорными координатами, и полоска «телепортировалась» бы
        self._stop_timer("_flush")
        if self._pending_x is not None:
            x = self._pending_x
            self._pending_x = None
            self._set_from_x(x)
        self._drag = False
        self.capture_mouse(False)
        event.stop()

    def _stop_timer(self, name: str):
        timer = getattr(self, name, None)
        if timer is not None:
            timer.stop()
            setattr(self, name, None)

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
        self._wheel(+1, event)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        self._wheel(-1, event)

    def _wheel(self, direction: int, event):
        """Колесо: шаг копится и применяется тиками, а не пачкой за кадр.

        Один «щелчок» колеса на обычной мыши = одно событие, оно
        применяется сразу (отклик мгновенный); тачпад/гладкое колесо шлёт
        десятки событий подряд — они сворачиваются в WHEEL_MAX шагов за
        WHEEL_DT, поэтому значение едет ровно, а не прыгает на десятки.
        """
        event.stop()
        if self.max <= self.min:
            return
        limit = WHEEL_BACKLOG * self.step
        self._wheel_pending = max(
            -limit, min(limit, self._wheel_pending + direction * self.step)
        )
        if self._wheel_timer is not None:
            return  # долг уже ждёт своего тика
        if time.monotonic() - self._last_wheel >= WHEEL_DT:
            self._apply_wheel()
        else:
            self._wheel_timer = self.set_timer(WHEEL_DT, self._apply_wheel)

    def _apply_wheel(self):
        self._wheel_timer = None
        if self._wheel_pending == 0.0:
            return
        cap = WHEEL_MAX * self.step
        part = max(-cap, min(cap, self._wheel_pending))
        self._wheel_pending -= part
        self._last_wheel = time.monotonic()
        self.set_value(self.value + part, notify=True)
        if self._wheel_pending != 0.0 and self.is_running:
            self._wheel_timer = self.set_timer(WHEEL_DT, self._apply_wheel)

    def watch_value(self, value: float):
        self.refresh()

    def on_unmount(self):
        self._stop_timer("_flush")
        self._stop_timer("_wheel_timer")
        self._pending_x = None
        self._drag = False


MiniSlider = AsciiSlider


class SineWave(Widget):
    """Живая синусоида с интерактивными стопами градиента.

    Верхняя строка — четыре метки: «+» (пусто, клик = добавить цвет) и
    «●» (стоп, клик = заменить/удалить). Тело волны окрашено петлёй
    grad.color_at(x/width + color_step): color_step двигается тем же шагом,
    что и клавиатура (демон отдаёт k/steps), поэтому «перелив» на экране
    совпадает с тем, что реально уходит в EC.
    """

    class StopClicked(Message):
        def __init__(self, wave: "SineWave", index: int) -> None:
            super().__init__()
            self.wave = wave
            self.index = index

    period = reactive(0.0)
    speed = reactive(1.0)
    phase = reactive(0.0)

    FLOW_TICK = 0.04  # тик офлайн-потока, с (25 Гц — предел обновления UI)
    TICK = 0.12       # тик физики волны: амплитуда/период/перелив

    def __init__(
        self,
        slots=None,
        base=(255, 255, 255),
        speed: float = 1.0,
        *,
        slots_count: int = 4,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        from tui import core

        self._core = core
        self.slots_count = slots_count
        self.slots = list(slots or [])[:slots_count]
        while len(self.slots) < slots_count:
            self.slots.append(None)
        self.base = tuple(base)
        self.color_step = 0.0
        self._step_target = 0.0
        self._flow_step = 0.0
        self.auto_flow = False
        self._calm = True
        self._energy = 0.0
        self._energy_target = 0.0
        self._timer = None
        self._flow = None
        self.speed = float(speed)
        # амплитуда и «частота» волн от Effect Speed — с плавным лерпом
        self._amp_k, self._period_div = self._speed_targets()

    # --- состояние ------------------------------------------------------------

    def _speed_u(self) -> float:
        """Положение скорости в диапазоне 0.2..5.0 по логарифмической шкале."""
        sp = min(5.0, max(0.2, float(self.speed)))
        return (math.log(sp) - math.log(0.2)) / (math.log(5.0) - math.log(0.2))

    def _speed_targets(self) -> tuple:
        """(целевая амплитуда, целевой делитель периода) от скорости.

        Медленно = низкие волны и длинная дуга, быстро = выше и чаще.
        """
        u = self._speed_u()
        return 0.60 + 0.40 * u, 1.20 + 0.60 * u

    def set_slots(self, slots) -> None:
        self.slots = list(slots or [])[: self.slots_count]
        while len(self.slots) < self.slots_count:
            self.slots.append(None)
        self.refresh()

    def set_color_step(self, step: float) -> None:
        """Задать цель переливания; само значение доезжает в _tick плавно."""
        step = float(step) % 1.0
        if abs(((step - self._step_target) + 0.5) % 1.0 - 0.5) < 1e-6:
            return
        self._step_target = step
        self.refresh()

    def set_auto_flow(self, enabled: bool) -> None:
        self.auto_flow = bool(enabled)
        if self._flow is not None:
            self._flow.stop()
            self._flow = None
        if self.auto_flow:
            self._start_flow()

    def set_calm(self, enabled: bool) -> None:
        """Спокойный режим: мелкие ровные колыхания без переливов.

        Включается, когда эффект выключен — волна не замирает, но и не
        «кипит»: амплитуда и скорость фазы плавно уходят к мягкой базе.
        """
        self._calm = bool(enabled)
        self._energy_target = 0.0 if self._calm else 1.0
        if self._calm:
            self.set_auto_flow(False)
        self.refresh()

    @property
    def energy(self) -> float:
        """0 = спокойный режим, 1 = боевой (эффект запущен)."""
        return self._energy

    def _start_flow(self) -> None:
        if not self.is_mounted:
            return
        if self._flow is not None:
            self._flow.stop()
        # Тик фиксированный (UI дёргается не чаще 25 Гц), а доля петли за тик
        # считается от её периода LOOP_SECONDS/speed — ровно так же, как
        # период держит клавиатура (см. core.step_count): и офлайн-волна, и
        # EC идут с одинаковым темпом при любой скорости.
        sp = max(0.2, min(float(self.speed), 5.0))
        self._flow_step = self.FLOW_TICK * sp / self._core.LOOP_SECONDS
        self._flow = self.set_interval(self.FLOW_TICK, self._flow_tick)

    def _flow_tick(self) -> None:
        if not self.auto_flow:
            return
        self.set_color_step(self._step_target + self._flow_step)

    def _gradient(self):
        return self._core.Gradient(self.slots, base=self.base)

    # --- отрисовка -------------------------------------------------------------

    def _mark_x(self, index: int, width: int) -> int:
        return int(index * max(width - 1, 0) / max(self.slots_count - 1, 1))

    def on_mount(self):
        self._timer = self.set_interval(self.TICK, self._tick)
        if self.auto_flow:
            self._start_flow()

    def _tick(self):
        if self._energy != self._energy_target:
            d = self._energy_target - self._energy
            self._energy = self._energy_target if abs(d) <= 0.08 else self._energy + (0.08 if d > 0 else -0.08)
            self.refresh()
        # амплитуда/период тянутся к цели от скорости — без рывков
        amp_t, div_t = self._speed_targets()
        moved = False
        for name, target, step in (
            ("_amp_k", amp_t, 0.06),
            ("_period_div", div_t, 0.05),
        ):
            cur = getattr(self, name)
            d = target - cur
            if abs(d) <= step:
                new = target
            else:
                new = cur + (step if d > 0 else -step)
            if new != cur:
                setattr(self, name, new)
                moved = True
        if moved:
            self.refresh()
        # переливание: доезжаем к цели коротким путём, без рывков.
        # Предел шага должна успевать за целью: цель идёт со скоростью
        # speed/LOOP_SECONDS петли в секунду — при старом жёстком 0.04
        # волна отставала уже на speed ≳ 1.3 и «прыгала» хвостом.
        if abs(((self._step_target - self.color_step) + 0.5) % 1.0 - 0.5) > 1e-6:
            d = (self._step_target - self.color_step + 0.5) % 1.0 - 0.5
            cap = max(0.04, 1.6 * self.TICK * max(self.speed, 0.2)
                      / self._core.LOOP_SECONDS)
            self.color_step = (self.color_step + max(-cap, min(cap, d))) % 1.0
            self.refresh()
        # фаза: в боевом режиме быстрее, в спокойном — тихий медленный ход
        rate = (0.06 + 0.16 * self._energy) * max(self.speed, 0.05)
        self.phase = (self.phase + rate) % (2 * math.pi)

    def render(self) -> Text:
        width = max(self.size.width, 4)
        height = max(self.size.height, 1)
        grad = self._gradient()
        marker_row = height >= 4
        body_h = height - (1 if marker_row else 0)
        text = Text()

        if marker_row:
            cells = []
            for x in range(width):
                idx = min(
                    range(self.slots_count),
                    key=lambda i: abs(self._mark_x(i, width) - x),
                )
                color = self.slots[idx] if idx < len(self.slots) else None
                if abs(self._mark_x(idx, width) - x) > 0:
                    cells.append((" ", ""))
                elif color:
                    cells.append(("●", f"bold {color}"))
                else:
                    cells.append(("+", "dim"))
            for ch, style in cells:
                text.append(ch, style=style)

        mid = (body_h - 1) / 2.0
        e = self._energy
        # амплитуда: скорость тянет её вверх/вниз (плавно, через _tick),
        # энергия режима — множитель боевого/спокойного состояния.
        # В покое множитель почти 0: линия ровная, но фаза слегка её
        # поднимает/опускает — видно, что синус живой, а не зависший.
        amp = (max(mid, 0.5) + 0.5) * self._amp_k * (0.10 + 0.90 * e)
        if e > 0.5 and body_h >= 4:
            # минимум (с запасом под дробный sin), чтобы между осью и кривой
            # оставалась хотя бы одна заполненная строка — иначе волна
            # вырождается в линию без █
            amp = max(amp, (int(mid) + 2) - mid + 0.5)
        else:
            # покой: почти плоско, но ростка хватает, чтобы вершина чуть
            # выходила за ось — видно, что линия живая, а не зависшая
            amp = max(amp, 0.55)
        period = self.period if self.period >= 4.0 else float(width) / self._period_div
        rows = [[" "] * width for _ in range(body_h)]
        styles = [[None] * width for _ in range(body_h)]

        def row_of(y: float) -> int:
            return min(body_h - 1, max(0, int(y)))

        def glyph(y: float) -> str:
            row = row_of(y)
            frac = min(1.0, max(0.0, y - row))
            return RAMP[max(0, min(7, int(frac * 8)))]

        def put(x: int, y: int, char: str, style: str | None = None):
            if 0 <= x < width and 0 <= y < body_h:
                rows[y][x] = char
                if style is not None:
                    styles[y][x] = style

        def blend(a, b, t):
            return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

        mid_row = row_of(mid)
        # почти плоская волна: на оси оставляем саму линию, а не блок-глифы —
        # тогда покой читается как ровная черта с редкими толчками
        flat = amp < 1.0
        for x in range(width):
            u = x / float(width)
            # боевой режим переливает градиент (color_step), спокойный —
            # держит статичный оттенок; между ними плавный lerp по energy
            moving = grad.color_at((u + self.color_step) % 1.0)
            still = grad.color_at(u)
            hexv = self._core.to_hex(blend(still, moving, e))
            style = f"bold {hexv}"
            soft = f"dim {hexv}"
            y = mid + amp * math.sin((2 * math.pi * x) / period + self.phase)
            y = max(0.0, min(float(body_h) - 1e-6, y))
            row = row_of(y)
            step = 1 if row > mid_row else -1
            for between in range(mid_row + step, row, step):
                put(x, between, "█", soft)
            if styles[mid_row][x] is None:
                # ось приглушена (в бою её почти перекрывает заливка), но
                # остаётся в цвете оттенка — линия не выгорает в серый
                put(x, mid_row, "─", hexv if e <= 0.5 else f"dim {hexv}")
            if not (flat and row == mid_row):
                put(x, row, glyph(y), style)

        for i, line in enumerate(rows):
            if marker_row or i:
                text.append("\n")
            for j, ch in enumerate(line):
                style = styles[i][j]
                text.append(ch, style=style if style else "")
        return text

    # --- интерактив ------------------------------------------------------------

    def on_click(self, event: events.Click) -> None:
        if self.size.width <= 0:
            return
        x = event.x
        idx = min(
            range(self.slots_count),
            key=lambda i: abs(self._mark_x(i, self.size.width) - x),
        )
        self.post_message(self.StopClicked(self, idx))
        event.stop()
        event.prevent_default()

    def watch_phase(self, phase: float):
        self.refresh()

    def watch_speed(self, speed: float):
        if self.auto_flow and self.is_mounted:
            self._start_flow()
        self.refresh()

    def on_unmount(self):
        for timer in (self._timer, self._flow):
            if timer is not None:
                timer.stop()
        self._timer = self._flow = None
