"""Shared logging for victus-suite tools.

Everything lives in ONE project folder:

    <project>/logs/victus.log          ← this log (rotated 512 KiB × 5)
    <project>/state/report-*.txt       ← victus-report output
    <project>/bin/                     ← executables
    <project>/docs/, TZ.md             ← docs

Log dir resolution:
    1. $VICTUS_LOG_DIR if set
    2. <project>/logs if this file lives in <project>/bin
    3. ~/.local/state/victus (XDG) otherwise

Level via env VICTUS_LOG = debug|info|warn|error  (default: info)
"""

import datetime
import errno
import os
import pwd
import traceback

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
MAX_BYTES = 512 * 1024

_HERE = os.path.dirname(os.path.realpath(__file__))
_PROJECT = os.path.dirname(_HERE) if os.path.basename(_HERE) == "bin" else None


def _home():
    user = os.environ.get("SUDO_USER")
    if user:
        try:
            return pwd.getpwnam(user).pw_dir
        except KeyError:
            pass
    return os.path.expanduser("~")


def project_dir():
    """Project root, or None if we are not running from the project tree."""
    if _PROJECT and os.path.isdir(_PROJECT):
        return _PROJECT
    return None


def config_dir():
    """Colors/profiles config dir: <project>/config or ~/.config/victus-kbd."""
    override = os.environ.get("VICTUS_CONFIG_DIR")
    if override:
        return override
    if project_dir():
        return os.path.join(project_dir(), "config")
    return os.path.join(_home(), ".config", "victus-kbd")


def log_dir():
    override = os.environ.get("VICTUS_LOG_DIR")
    if override:
        return override
    if project_dir():
        return os.path.join(project_dir(), "logs")
    return os.path.join(_home(), ".local", "state", "victus")


def state_dir():
    override = os.environ.get("VICTUS_STATE_DIR")
    if override:
        return override
    if project_dir():
        return os.path.join(project_dir(), "state")
    return os.path.join(_home(), ".local", "state", "victus")


def log_path():
    return os.path.join(log_dir(), "victus.log")


def _threshold():
    return LEVELS.get(os.environ.get("VICTUS_LOG", "info").lower(), 20)


def _rotate(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
            for i in range(4, 0, -1):
                src = f"{path}.{i}" if i > 1 else path
                dst = f"{path}.{i + 1}" if i > 1 else f"{path}.1"
                if os.path.exists(dst):
                    os.unlink(dst)
                if os.path.exists(src):
                    os.rename(src, dst)
    except OSError:
        pass


def _fix_owner(path):
    """When root writes the log (sudo), keep the file owned by the project owner."""
    if os.geteuid() != 0:
        return
    try:
        owner_dir = project_dir() or os.path.dirname(path)
        st = os.stat(owner_dir)
        if os.stat(path).st_uid != st.st_uid:
            os.chown(path, st.st_uid, st.st_gid)
    except OSError:
        pass


def log(level, tool, msg, exc=False):
    if LEVELS.get(level, 20) < _threshold():
        return
    path = log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _rotate(path)
        ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        uid = os.geteuid()
        line = f"{ts} {level.upper():<5} pid={os.getpid()} euid={uid} {tool}: {msg}\n"
        if exc:
            for tb in traceback.format_exc().strip().splitlines():
                line += f"{ts} {level.upper():<5} {'':>12}   | {tb}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        _fix_owner(path)
    except OSError as e:
        if e.errno != errno.EACCES:
            pass


def log_error(tool, msg, exc=True):
    log("error", tool, msg, exc=exc)


def log_info(tool, msg):
    log("info", tool, msg)


def log_debug(tool, msg):
    log("debug", tool, msg)


def log_exception(tool, msg):
    log("error", tool, msg, exc=True)
