"""Ядро victus-suite: состояние, градиент, каналы, разговор с фоновым демоном.

Один источник правды для TUI (bin/tui/*) и демона (bin/victusd):
  * состояние  — state/last_state.json (цвет, режим, скорость, стопы, яркость);
  * градиент   — 4 слота стопов → плавная петля цвета (косинусная интерполяция);
  * запись     — всегда через victus-kbd: сначала ipc-сокет демона, иначе локально.

Клавиатура пишется одним процессом (victus-kbd cycle), поэтому «что на экране»
и «что ушло в EC» считается одной и той же функцией samples[k].
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess

import victus_log as vlog

TOOL = "victus_core"
_HERE = os.path.dirname(os.path.realpath(__file__))
_BIN = os.path.dirname(_HERE)
BACKEND = os.path.join(_BIN, "victus-kbd")
DAEMON = os.path.join(_BIN, "victusd")
# Версия протокола/семантики состояния демона. Бампать при любом изменении
# ключей state или поведения (например, black_depth → brightness): TUI
# сверяет её через ping в ensure_daemon и перезапускает устаревший демон —
# иначе старый демон не знает новые ключи и перетирает запись TUI своим
# effective_rgb (см. запись 2026-10-01 18:xx в PROGRESS_LOG).
DAEMON_VERSION = "1.1"
STATE_FILE = os.path.join(vlog.state_dir(), "last_state.json")

QUICK = (
    "black", "white", "red", "green", "blue", "cyan",
    "magenta", "yellow", "orange", "purple", "pink", "gray",
)
SLOTS = 4
# Ступени петли: до 64 (по 16 промежуточных цветов на переход между стопами;
# раньше было 16 всего, т.е. по 4 — отсюда «резкое» переключение).
# Сколько ступеней реально уйдёт в петлю — step_count(): EC принимает не
# больше ~19 записей/с, поэтому на быстрых скоростях ступеней меньше, а
# период петли (LOOP_SECONDS/speed) сохраняется во всех случаях.
SAMPLES = 64          # максимум ступеней
MIN_SAMPLES = 16      # минимум: не меньше старого поведения (16 × 0.05 с)
LOOP_SECONDS = 4.0    # полная петля при speed=1 (не менялось: 16 × 0.25 с)
MIN_STEP_DELAY = 0.05  # пауза не ниже: замер — при меньшей EC «догоняет»
WRITE_COST = 0.004    # замер: запись в EC ≈ 2-4 мс при паузе ≥ 50 мс

DEFAULTS = {
    "rgb": [255, 255, 255],
    "hex": "#ffffff",
    "power": True,
    "effect": "none",
    "speed": 1.0,
    "stops": [None, None, None, None],
    "brightness": 100,
    "running": False,
    # режим питания: "normal" | "typewriter" (вкладка «Питание»)
    "power_mode": "normal",
}


def display_colors() -> dict:
    """Список пресетов для левой колонки: только базовые QUICK + свои.

    Прочие 38 оттенков BUILTIN в интерфейс не выносим — они остаются
    доступны по имени через CLI (victus-kbd <name>) и в пикере стопов нет.
    """
    import victus_palette as pal

    table = pal.all_colors()
    out = {name: table[name] for name in QUICK if name in table}
    for name, rgb in sorted(pal.load_custom().items()):
        if name not in out:
            out[name] = rgb
    return out


def sock_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(base, f"victus-suite-{os.getuid()}.sock")

def sock_path_check() -> bool:
    """True, если сокет демона существует (только для проверок/логов)."""
    return os.path.exists(sock_path())



def is_dry() -> bool:
    return os.environ.get("VICTUS_DRY_RUN") == "1"


EC_PATH = "/sys/kernel/debug/ec/ec0/io"


def ec_writable() -> bool:
    """True, если в EC можно писать без sudo (udev-правило, группа, root)."""
    try:
        return os.path.exists(EC_PATH) and os.access(EC_PATH, os.W_OK)
    except OSError:
        return False


def needs_sudo() -> bool:
    """Нужен ли sudo для записи в EC.

    Если контроллер уже доступен юзеру — sudo не зовём вообще, иначе
    `sudo -n` без валидного кэша валит запись, хотя всё настроено.
    """
    if is_dry() or os.geteuid() == 0:
        return False
    return not ec_writable()


def _with_priv(cmd: list) -> list:
    return (["sudo", "-n"] + cmd) if needs_sudo() else list(cmd)


async def probe_access(timeout: float = 6.0) -> str:
    """Проверка доступа к контроллеру подсветки при старте.

    dry / root / direct  — писать можно сразу, без пароля;
    sudo                 — кэш sudo активен (NOPASSWD или sudo -v уже сделан);
    need-password        — нужен пароль один раз: sudo -v;
    error                — EC недоступен / нет модуля.
    """
    if is_dry():
        return "dry"
    if os.geteuid() == 0:
        return "root"
    if ec_writable():
        return "direct"
    rc, out, err = await _backend([], timeout=timeout)
    text = f"{err or ''} {out or ''}".lower()
    if rc == 0:
        return "sudo"
    if "password" in text or "пароль" in text:
        return "need-password"
    return "error"


def hw_rgb(timeout: float = 6.0) -> list | None:
    """Что реально лежит в EC прямо сейчас — глаз, а не память.

    state/last_state.json — это то, что мы ЗАПИСАЛИ. Физически подсветку
    мог выключить кто угодно: клавиша на корпусе, чужой процесс, сброс
    после сна. Поэтому вкладка спрашивает железо, а не файл, иначе
    «свет выключен, а в программе горит».
    """
    try:
        proc = subprocess.run(["sudo", "-n", BACKEND, "get"],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    parts = (proc.stdout or "").split()
    if len(parts) < 3:
        return None
    try:
        return [int(float(parts[i])) for i in range(3)]
    except ValueError:
        return None


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    state = dict(DEFAULTS)
    if isinstance(data, dict):
        state.update({k: v for k, v in data.items() if k in DEFAULTS})
        if "brightness" not in data and "black_depth" in data:
            # миграция со старого ключа «темнота» (50 = база) на уровень
            # яркости (100 = полная сила): старое «50» означало обычный свет
            state["brightness"] = _clamp(int(_num(data.get("black_depth"), 50)) * 2, 0, 100)
    state["rgb"] = _norm_rgb(state.get("rgb"), DEFAULTS["rgb"])
    state["brightness"] = _clamp(int(_num(state.get("brightness"), 100)), 0, 100)
    state["speed"] = _clamp(float(_num(state.get("speed"), 1.0)), 0.2, 5.0)
    state["power"] = bool(state.get("power", True))
    state["effect"] = state.get("effect") if state.get("effect") in ("none", "cycle", "fade") else "none"
    state["running"] = bool(state.get("running", False))
    state["power_mode"] = (state.get("power_mode")
                           if state.get("power_mode") in ("normal", "typewriter")
                           else "normal")
    state["stops"] = norm_stops(state.get("stops"))
    state["hex"] = to_hex(tuple(state["rgb"]))
    return state


def save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        vlog.log("warn", TOOL, f"state save failed: {e}")


def _num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _norm_rgb(value, default=(255, 255, 255)):
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return [_clamp(int(c), 0, 255) for c in value]
        except (TypeError, ValueError):
            pass
    return list(default)


def _norm_hex(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) == 6 and all(c in "0123456789abcdefABCDEF" for c in v):
        return "#" + v.lower()
    return None


def _as_rgb(value):
    """hex-строка | [r,g,b] | None → кортеж RGB (или None)."""
    if isinstance(value, str):
        return hex_to_rgb(value)
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(_clamp(int(c), 0, 255) for c in value)
        except (TypeError, ValueError):
            return None
    return None


def norm_stops(value, slots: int = SLOTS) -> list:
    """Слоты стопов в каноническом виде: список из `slots` hex-строк или None."""
    out = []
    if isinstance(value, (list, tuple)):
        for s in value[:slots]:
            rgb = _as_rgb(s)
            out.append(to_hex(rgb) if rgb else None)
    while len(out) < slots:
        out.append(None)
    return out


def to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(_clamp(int(c), 0, 255) for c in rgb))


def as_hex(color):
    """hex-строка | [r,g,b] → hex-строка (или None, если не разобранось)."""
    rgb = _as_rgb(color)
    return to_hex(rgb) if rgb else None


def hex_to_rgb(value):
    v = _norm_hex(value)
    if not v:
        return None
    v = v[1:]
    return [int(v[i:i + 2], 16) for i in (0, 2, 4)]


def apply_brightness(rgb, level) -> tuple:
    """Уровень подсветки: 100 = цвет в полную силу, 0 = свет выключен.

    Аппаратного байта яркости в железе нет (см. docs/03: WMI-событие
    HPWMI_BACKLIT_KB_BRIGHTNESS в Linux не пробрасывается, кандидат EC 0x29
    не подтверждён), поэтому сила света делается масштабированием цвета:
    диод физически светит слабее, оттенок при этом не меняется — раньше
    шкала 0/50/100 вымывала цвет в белый (см. сессию 2026-10-01 в
    PROGRESS_LOG), и красный превращался в розовый.
    """
    k = _clamp(int(_num(level, 100)), 0, 100) / 100.0
    return tuple(
        _clamp(int(round(_clamp(int(c), 0, 255) * k)), 0, 255) for c in rgb
    )


def delay_for_speed(speed: float) -> float:
    """Секунд на один шаг петли от Effect Speed.

    Направление то же, что у синусоиды (там rate *= speed): слайдер
    «Скорость» должен ускорять и волну, и клавиатуру одновременно.

    Шаг считается от периода петли, а не задаётся числом:
        delay = (LOOP_SECONDS / SAMPLES) / speed
    т.е. при speed=1 это 0.0625 с на ступень. Пауза при этом не опускается
    ниже MIN_STEP_DELAY (замер: при меньшей паузе запись в EC «догоняет» и
    шаг растягивается до ~50-58 мс — теряем только в точности тайминга).
    Число ступеней под период подбирает step_count().
    """
    sp = _clamp(_num(speed, 1.0), 0.2, 5.0)
    return _clamp((LOOP_SECONDS / SAMPLES) / sp, MIN_STEP_DELAY, 2.0)


def step_count(speed: float, delay: float | None = None) -> int:
    """Сколько ступеней влезает в петлю LOOP_SECONDS/speed.

    Реальная ступень = пауза + запись в EC (WRITE_COST), поэтому
        n = round((LOOP_SECONDS / speed) / (delay + WRITE_COST))
    На speed ≤ 1 даёт все SAMPLES (64), на speed=5 — 16, т.е. ровно то,
    что крутилось раньше: железо не быстрее, но и не медленнее.
    """
    sp = _clamp(_num(speed, 1.0), 0.2, 5.0)
    d = delay_for_speed(sp) if delay is None else float(delay)
    per = max(_num(d, MIN_STEP_DELAY), MIN_STEP_DELAY) + WRITE_COST
    n = int(round((LOOP_SECONDS / sp) / per))
    return int(_clamp(n, MIN_SAMPLES, SAMPLES))


class Gradient:
    """Петля из 4 слотов (равномерно, с замыканием последнего на первый)."""

    def __init__(self, stops=None, base=(255, 255, 255)):
        self.slots = norm_stops(stops)
        self.base = tuple(_norm_rgb(base, (255, 255, 255)))

    @property
    def colors(self) -> list:
        out = []
        for c in self.slots:
            rgb = _as_rgb(c)
            if rgb:
                out.append(rgb)
        return out

    def set_slot(self, index: int, color) -> None:
        if 0 <= index < SLOTS:
            rgb = _as_rgb(color)
            self.slots[index] = to_hex(rgb) if rgb else None

    def color_at(self, t: float) -> tuple:
        cols = self.colors
        if not cols:
            return tuple(self.base)
        if len(cols) == 1:
            return cols[0]
        pos = (float(t) % 1.0) * len(cols)
        i = int(pos)
        frac = pos - i
        a = cols[i % len(cols)]
        b = cols[(i + 1) % len(cols)]
        ease = 0.5 - 0.5 * __import__("math").cos(frac * 3.141592653589793)
        return tuple(round(a[j] + (b[j] - a[j]) * ease) for j in range(3))

    def samples(self, n: int = SAMPLES) -> list:
        cols = self.colors
        if not cols:
            return [tuple(self.base)] * n
        return [self.color_at(i / n) for i in range(n)]

    def hex_slots(self) -> list:
        return list(self.slots)


def fade_samples(rgb, n: int = SAMPLES) -> list:
    """Fade: плавный разгон цвета до черного и обратно."""
    base = tuple(_norm_rgb(rgb))
    out = []
    import math
    for i in range(n):
        b = (1.0 - math.cos(2.0 * math.pi * i / n)) / 2.0
        out.append(tuple(round(c * b) for c in base))
    return out


async def _backend(args, timeout=12.0):
    cmd = _with_priv([BACKEND] + [str(a) for a in args])
    vlog.log_info(TOOL, f"backend {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return 124, "", "timeout"
    except OSError as e:
        return 127, "", str(e)
    return proc.returncode, out.decode().strip(), err.decode().strip()


def ec_module_ok() -> bool:
    """Загружен ли ec_sys с write_support=1.

    /sys/module читается юзером без root — этим отличаем «модуля нет»
    от «модуль есть, но debugfs закрыт для юзера».
    """
    try:
        with open("/sys/module/ec_sys/parameters/write_support", encoding="utf-8") as f:
            return f.read().strip() == "Y"
    except OSError:
        return False


def access_hint(verdict: str) -> str:
    """Что сказать пользователю, когда доступа к EC нет.

    Ложные требования убраны: modprobe предлагаем только если модуля
    действительно нет, иначе — реальная причина (debugfs закрыт для юзера).
    """
    from i18n import t

    if verdict in ("dry", "root", "direct", "sudo"):
        return ""
    if ec_module_ok():
        return t("tui.need_sudo")
    return t("tui.access_error")


def _sudo_hint(text: str) -> str:
    """Ошибку бэкенда переводим в понятную подсказку, но не выдумываем.

    Право/пароль/модуль определяем по факту (ec_module_ok), а не по словам —
    иначе просим modprobe там, где модуль уже загружен.
    """
    low = (text or "").lower()
    if any(s in low for s in ("password", "пароль", "sudo", "root", "прав")):
        return access_hint("error")
    if any(s in low for s in ("ec_sys", "ec interface", "интерфейс ec",
                              "ec недоступен", "/sys/kernel/debug")):
        return access_hint("error")
    return text or ""


def colors_for_state(state: dict) -> list:
    """Петля для режима: cycle = градиент стопов, fade = разгон до черного.

    На выходе — уже с уровнем яркости: клавиатура получает финальный цвет.
    Длина петли — step_count(speed): ступеней максимум, сколько влезает
    в период LOOP_SECONDS/speed с учётом потолка EC.
    """
    n = step_count(state.get("speed", 1.0))
    if state.get("effect") == "fade":
        raw = fade_samples(state.get("rgb", (255, 255, 255)), n)
    else:
        grad = Gradient(state.get("stops"), base=state.get("rgb", (255, 255, 255)))
        raw = grad.samples(n)
    level = state.get("brightness", 100)
    return [to_hex(apply_brightness(c, level)) for c in raw]


async def local_apply(rgb) -> tuple:
    rc, out, err = await _backend([",".join(str(c) for c in rgb)])
    if rc != 0:
        return False, _sudo_hint(err or out) or f"rc={rc}"
    return True, ""


async def local_effect_start(colors, delay: float) -> tuple:
    hexes = [h for h in (as_hex(c) for c in colors) if h]
    if not hexes:
        return False, "no colors"
    rc, out, err = await _backend(["cycle", *hexes, "--delay", f"{delay:.3f}", "--bg"])
    if rc != 0:
        return False, _sudo_hint(err or out) or f"rc={rc}"
    return True, out


async def local_effect_stop() -> tuple:
    rc, out, err = await _backend(["stop"])
    if rc != 0:
        return False, _sudo_hint(err or out) or f"rc={rc}"
    return True, out


def stop_effect_sync(timeout: float = 4.0) -> tuple:
    """Синхронная остановка петли при выходе: сначала демон, потом напрямую.

    Нужна в on_unmount (там asyncio уже закрывается), чтобы закрытие окна
    не оставляло victus-kbd cycle фоном.
    """
    reply = request_sync("effect_stop", timeout=timeout)
    if reply is not None:
        return bool(reply.get("ok")), reply.get("msg", "")
    cmd = _with_priv([BACKEND, "stop"])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    out = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, out


def request_sync(cmd: str, timeout: float = 1.5, **payload) -> dict | None:
    """Синхронный запрос к демону — для CLI/трей, вне цикла asyncio."""
    path = sock_path()
    if not os.path.exists(path):
        return None
    msg = {"cmd": cmd}
    msg.update(payload)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
        sock.sendall((json.dumps(msg) + "\n").encode())
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break
        raw = b"".join(chunks).split(b"\n", 1)[0]
        return json.loads(raw.decode() or "{}")
    except (OSError, ValueError) as e:
        vlog.log("warn", TOOL, f"ipc-sync {cmd} failed: {e}")
        return None
    finally:
        sock.close()


class Engine:
    """Пишет в клавиатуру: ipc-сокет демона, а если его нет — напрямую."""

    def __init__(self):
        self._online = False

    @property
    def online(self) -> bool:
        return self._online

    async def request(self, cmd: str, **payload) -> dict | None:
        msg = {"cmd": cmd}
        msg.update(payload)
        path = sock_path()
        if not os.path.exists(path):
            self._online = False
            return None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(path), timeout=1.5
            )
            writer.write((json.dumps(msg) + "\n").encode())
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=1.5)
            writer.close()
            await writer.wait_closed()
            data = json.loads(raw.decode() or "{}")
        except (OSError, ValueError, asyncio.TimeoutError) as e:
            self._online = False
            vlog.log("warn", TOOL, f"ipc {cmd} failed: {e}")
            return None
        self._online = True
        return data

    async def ping(self) -> bool:
        data = await self.request("ping")
        return bool(data and data.get("ok"))

    async def hello(self) -> dict | None:
        """Полный ответ ping (version, pid, state) — проверка версии демона."""
        return await self.request("ping")

    async def status(self) -> dict | None:
        return await self.request("status")

    async def push_state(self, state: dict) -> dict | None:
        return await self.request("set", state=state)

    async def kill_loop(self) -> tuple:
        """Гасит петлю и у демона, и напрямую — на случай чужого цикла.

        Демон мог не знать о запущенном `victus-kbd cycle` (перезапуск,
        чужой процесс), поэтому локальный stop зовём всегда.
        """
        await self.request("effect_stop")
        return await local_effect_stop()

    async def apply(self, rgb, effective=None) -> tuple:
        """Ручной цвет: пишет напрямую в EC, минуя демон.

        rgb — исходный цвет, effective — что реально уходит в EC
        (power/brightness). Петля гасится отдельно (kill_loop) ДО push
        state, иначе демон при `set` перезапустит цикл поверх цвета.
        Прямая запись идёт первой (мгновенно), затем демон синхронизирует
        своё state, чтобы status/restore показывали тот же цвет.
        """
        ok, msg = await local_apply(rgb if effective is None else effective)
        if not self._online:
            return ok, msg
        data = await self.request("apply", rgb=list(rgb))
        if data is not None and bool(data.get("ok")):
            return True, ""
        if data is not None and not ok:
            return False, data.get("msg", "")
        return ok, msg

    async def effect_start(self, colors, delay: float, effect: str = "cycle") -> tuple:
        hexes = [h for h in (as_hex(c) for c in colors) if h]
        data = await self.request(
            "effect_start", colors=hexes, delay=delay, effect=effect
        )
        if data is not None:
            return bool(data.get("ok")), data.get("msg", "")
        return await local_effect_start(colors, delay)

    async def effect_stop(self) -> tuple:
        data = await self.request("effect_stop")
        if data is not None:
            return bool(data.get("ok")), data.get("msg", "")
        return await local_effect_stop()


def spawn_daemon() -> int | None:
    try:
        proc = subprocess.Popen(
            [DAEMON],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as e:
        vlog.log_error(TOOL, f"daemon spawn failed: {e}", exc=False)
        return None
    vlog.log_info(TOOL, f"daemon spawned pid={proc.pid}")
    return proc.pid


async def ensure_daemon(timeout: float = 4.0) -> bool:
    """Поднять демон; живой, но устаревший — перезапустить под новый код.

    Старый демон не знает новые ключи state (свой effective_rgb перетирает
    запись TUI: уровень яркости «не работает», свет возвращается сам) —
    поэтому по ответу ping сверяем версию и, если она не совпадает,
    просим демон выйти и поднимаем заново.
    """
    path = sock_path()
    if os.path.exists(path):
        engine = Engine()
        info = await engine.hello()
        if info and info.get("ok"):
            if info.get("version") == DAEMON_VERSION:
                return True
            vlog.log_info(
                TOOL, f"daemon version {info.get('version')!r} != "
                      f"{DAEMON_VERSION!r} — restart"
            )
            await engine.request("quit")
            loop = asyncio.get_event_loop()
            deadline = loop.time() + 3.0
            while loop.time() < deadline and os.path.exists(path):
                if not await Engine().ping():
                    break
                await asyncio.sleep(0.1)
        try:
            os.unlink(path)
        except OSError:
            pass
    spawn_daemon()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.1)
        if os.path.exists(path) and await Engine().ping():
            return True
    return False
