"""Single source of truth for keyboard backlight colors.

BUILTIN palette + user colors from config/colors.conf.
Used by victus-kbd, Changer and ColorMaker — never duplicate the palette.

Color spaces: RGB tuples (0..255), HSV degrees/0..1, HEX "#rrggbb".
Helpers for TUI gradient / color-picker: gradient(), mix(), adjust().
"""

import colorsys
import os
import re

import victus_log as vlog

TOOL = "victus_palette"

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

BUILTIN = {
    "red": (255, 0, 0),
    "fire": (255, 50, 0),
    "scarlet": (255, 20, 20),
    "darkred": (139, 0, 0),
    "crimson": (220, 20, 60),
    "maroon": (128, 0, 0),
    "wine": (114, 47, 55),
    "green": (0, 255, 0),
    "lime": (0, 255, 0),
    "neongreen": (57, 255, 20),
    "blue": (0, 0, 255),
    "navy": (0, 0, 128),
    "skyblue": (135, 206, 235),
    "iceblue": (99, 203, 255),
    "teal": (0, 128, 128),
    "turquoise": (64, 224, 208),
    "yellow": (255, 255, 0),
    "gold": (255, 215, 0),
    "orange": (255, 165, 0),
    "coral": (255, 127, 80),
    "salmon": (250, 128, 114),
    "purple": (128, 0, 128),
    "magenta": (255, 0, 255),
    "violet": (143, 0, 255),
    "indigo": (75, 0, 130),
    "pink": (255, 105, 180),
    "hotpink": (255, 20, 147),
    "lightpink": (255, 192, 203),
    "rose": (255, 0, 127),
    "neonpink": (255, 24, 160),
    "neonpurple": (191, 64, 255),
    "orchid": (218, 112, 214),
    "plum": (221, 160, 221),
    "lavender": (230, 230, 250),
    "cyan": (0, 255, 255),
    "brown": (165, 42, 42),
    "tan": (210, 180, 140),
    "beige": (245, 245, 220),
    "ivory": (255, 255, 240),
    "chocolate": (210, 105, 30),
    "gray": (128, 128, 128),
    "silver": (192, 192, 192),
    "olive": (128, 128, 0),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "warmwhite": (255, 244, 229),
    "coolwhite": (220, 240, 255),
    "off": (0, 0, 0),
}


def conf_path():
    return os.path.join(vlog.config_dir(), "colors.conf")


def load_custom(path=None):
    path = path or conf_path()
    colors = {}
    if not os.path.exists(path):
        return colors
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            raw = line.rstrip("\n")
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                vlog.log("warn", TOOL, f"{path}:{lineno}: no '=' in {raw!r}")
                continue
            name, val = line.split("=", 1)
            name = name.strip()
            if not NAME_RE.match(name):
                vlog.log("warn", TOOL, f"{path}:{lineno}: bad name {name!r}")
                continue
            try:
                rgb = tuple(int(x) for x in val.split(","))
            except ValueError:
                vlog.log("warn", TOOL, f"{path}:{lineno}: bad rgb {val!r}")
                continue
            if len(rgb) == 3 and all(0 <= v <= 255 for v in rgb):
                colors[name] = rgb
            else:
                vlog.log("warn", TOOL, f"{path}:{lineno}: out of range {rgb}")
    return colors


def all_colors(path=None):
    colors = dict(BUILTIN)
    colors.update(load_custom(path))
    return colors


def parse(token, colors=None):
    """Name / #RRGGBB / #RGB / r,g,b / hsv(h,s,v) / hsl(h,s%,l%) -> (r,g,b) or None."""
    low = token.lower().strip()
    table = all_colors() if colors is None else colors
    if low in table:
        return table[low]
    if low.startswith("#"):
        return hex_to_rgb(low)
    if low.startswith(("hsv(", "hsl(")) and low.endswith(")"):
        return hsv_token_to_rgb(low)
    if "," in low:
        try:
            parts = tuple(int(x) for x in low.split(","))
        except ValueError:
            return None
        if len(parts) == 3 and all(0 <= v <= 255 for v in parts):
            return parts
    return None


def hex_to_rgb(token):
    """#rrggbb or #rgb -> (r,g,b), else None."""
    h = token[1:] if token.startswith("#") else token
    if len(h) == 3 and all(c in "0123456789abcdef" for c in h.lower()):
        h = "".join(c * 2 for c in h.lower())
    if len(h) != 6 or not all(c in "0123456789abcdef" for c in h.lower()):
        return None
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hsv_token_to_rgb(token):
    """'hsv(300,0.7,1)' / 'hsl(300,70%,50%)' -> (r,g,b), else None."""
    kind = token[:3]
    body = token[4:-1]
    try:
        h, s, x = (float(p.strip().rstrip("%")) for p in body.split(","))
    except ValueError:
        return None
    s = s / 100.0 if s > 1 else s
    x = x / 100.0 if x > 1 else x
    h = h % 360.0
    s = min(max(s, 0.0), 1.0)
    x = min(max(x, 0.0), 1.0)
    if kind == "hsl":
        r, g, b = colorsys.hls_to_rgb(h / 360.0, x, s)
    else:
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, x)
    return rgb(r * 255, g * 255, b * 255)


def rgb(*vals):
    """Clamp floats/ints to a valid (r,g,b) tuple of ints 0..255."""
    if len(vals) == 1:
        vals = tuple(vals[0])
    return tuple(int(min(max(round(v), 0), 255)) for v in vals)


def rgb_to_hsv(color):
    """(r,g,b) -> (h 0..360, s 0..1, v 0..1)."""
    r, g, b = (c / 255.0 for c in color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360.0, s, v)


def hsv_to_rgb(h, s, v):
    """(h 0..360, s 0..1, v 0..1) -> (r,g,b). Wraps hue, clamps s/v."""
    h = (h % 360.0) / 360.0
    s = min(max(s, 0.0), 1.0)
    v = min(max(v, 0.0), 1.0)
    return rgb(*(c * 255 for c in colorsys.hsv_to_rgb(h, s, v)))


def adjust(color, dh=0.0, ds=0.0, dv=0.0):
    """Shift a color in HSV space. dv/ds are additive, dh in degrees."""
    h, s, v = rgb_to_hsv(color)
    return hsv_to_rgb(h + dh, s + ds, v + dv)


def with_value(color, v):
    """Same hue/saturation, new brightness v (0..1)."""
    h, s, _ = rgb_to_hsv(color)
    return hsv_to_rgb(h, s, v)


def mix(a, b, t):
    """Linear interpolation between two colors, t in 0..1."""
    t = min(max(t, 0.0), 1.0)
    return rgb(*[a[i] + (b[i] - a[i]) * t for i in range(3)])


def gradient(stops, steps):
    """Evenly interpolate a color list into `steps` colors (for TUI preview)."""
    if steps < 2:
        return [tuple(stops[0])]
    if len(stops) == 1:
        return [tuple(stops[0])] * steps
    out = []
    seg = len(stops) - 1
    for i in range(steps):
        pos = i / (steps - 1) * seg
        idx = min(int(pos), seg - 1)
        out.append(mix(stops[idx], stops[idx + 1], pos - idx))
    return out


def fmt(rgb_color):
    return f"{rgb_color[0]},{rgb_color[1]},{rgb_color[2]}"


def to_hex(rgb_color):
    return "#{:02x}{:02x}{:02x}".format(*rgb_color)

