#!/usr/bin/env python3
"""Офлайн-тесты fanlib: фильтр температур, гистерезис SMART, одноканальный PWM.

Без железа: hwmon подменяется временным каталогом, пресет — словарём.
Запуск:  pytest vertil/tools/lab/test_fanlib.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import fanlib as F  # noqa: E402


# --------------------------------------------------------------------------- #
# TempFilter
# --------------------------------------------------------------------------- #
def test_filter_rejects_single_spike():
    """Одиночный скачок (пик TCPU_PCI) не должен пройти через медиану-3."""
    f = F.TempFilter(window=3, rise=100.0, fall=100.0)   # slew не мешает
    out = [f.update(v) for v in (70, 70, 70, 95, 70, 70, 70)]
    assert max(out) <= 70, "медиана-3 пропустила одиночный пик"
    assert out[-1] == 70


def test_filter_needs_two_of_three():
    """Пик, держащийся 2 снимка из 3, проходит — это уже не выброс."""
    f = F.TempFilter(window=3, rise=100.0, fall=100.0)
    out = [f.update(v) for v in (70, 70, 95, 95, 70)]
    assert max(out) > 70


def test_filter_slew_limits_rate():
    """Сlew-лимит ограничивает dT/dt — именно его видит экстраполяция."""
    f = F.TempFilter(window=1, rise=5.0, fall=5.0)
    f.update(50)
    out = f.update(90)                      # цель 90, но за один снимок ≤5
    assert out == 55
    assert f.update(90) == 60


def test_filter_keeps_last_on_sensor_glitch():
    f = F.TempFilter(window=3, rise=10.0, fall=10.0)
    assert f.update(60) == 60
    assert f.update(None) == 60, "мигание датчика не должно обнулять значение"


def test_filter_sustained_ramp_passes():
    """Настоящий разогрев доходит до цели — фильтр не съедает разгон."""
    f = F.TempFilter(window=3, rise=12.0, fall=6.0)
    vals = [50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
    out = [f.update(v) for v in vals]
    assert out[-1] >= 90
    assert out == sorted(out), "фильтр должен монотонно идти за разогревом"


# --------------------------------------------------------------------------- #
# Smart: гистерезис и авария
# --------------------------------------------------------------------------- #
def _preset(**smart_overrides) -> dict:
    preset = F.load_preset()
    preset = json.loads(json.dumps(preset))          # глубокая копия
    preset["smart"].update(smart_overrides)
    return preset


def _sensor(tc=60.0, tg=50.0, tv=60.0, **extra) -> dict:
    d = {"t_cpu": tc, "t_gpu": tg, "t_vrm": tv,
         "t_cpu_raw": tc, "t_gpu_raw": tg, "t_vrm_raw": tv}
    d.update(extra)
    return d


def test_hysteresis_blocks_small_steps_only():
    """Чистая функция гистерезиса: мелкие колебания держим, крупные пускаем."""
    h = F.Smart._hyst
    assert h(100.0, 60.0, up=5, down=8) == 100.0, "крупный разогрев обязан пройти"
    assert h(50.0, 60.0, up=5, down=8) == 50.0, "крупное остывание обязано пройти"
    assert h(62.0, 60.0, up=5, down=8) == 60.0, "шаг на 2 вверх должен держаться"
    assert h(55.0, 60.0, up=5, down=8) == 60.0, "шаг на 5 вниз должен держаться"
    assert h(40.0, None, up=5, down=8) == 40.0, "первый снимок не зажимается"


def test_smart_hysteresis_damps_oscillation():
    """Цель, дрожащая на границе полосы, перестаёт метаться туда-сюда."""
    temps = [52.4, 51.6] * 6          # вокруг cpu_band.low = 52.0

    def direction_changes(with_hyst: bool) -> int:
        over = {"hysteresis": {"up": 5, "down": 8}} if with_hyst else {
            "hysteresis": {"up": 0, "down": 0}}
        smart = F.Smart(_preset(**over), seed=(100, 100))
        prev_target, changes, last_sign = None, 0, 0
        for t in temps:
            smart.update(_sensor(tc=t), 1.0)
            target = smart.t1_h
            if prev_target is not None and target != prev_target:
                sign = 1 if target > prev_target else -1
                if last_sign and sign != last_sign:
                    changes += 1
                last_sign = sign
            prev_target = target
        return changes

    assert direction_changes(True) <= 1, "гистерезис не гасит дрожание цели"
    assert direction_changes(False) >= 3, "без гистерезиса цель должна метаться"


def test_smart_hysteresis_still_reacts_to_real_heat():
    preset = _preset(hysteresis={"up": 5, "down": 8})
    smart = F.Smart(preset, seed=(60, 60))
    smart.update(_sensor(tc=55.0), 1.0)
    p1, _, _, _ = smart.update(_sensor(tc=92.0), 1.0)
    assert p1 > 60, "гистерезис не должен блокировать настоящий разогрев"


def test_smart_emergency_uses_raw_temperature():
    """Фильтр не откладывает аварию: сработало по сырому значению."""
    preset = _preset()
    smart = F.Smart(preset, seed=(60, 60))
    smart.update(_sensor(tc=60.0), 1.0)
    # отфильтрованная ещё холодная, сырая уже аварийная
    p1, p2, act, _ = smart.update(_sensor(tc=60.0, t_cpu_raw=95.0), 1.0)
    assert p1 > 60 and p2 > 60, "авария не увидела сырую температуру"


def test_smart_respects_deadband():
    """На установившейся цели deadband глушит лишние записи в железо."""
    preset = _preset()
    smart = F.Smart(preset, seed=(100, 100))
    # даём контроллеру дойти до цели
    for _ in range(120):
        smart.update(_sensor(tc=60.0), 1.0)
    writes = []
    for _ in range(10):
        _, _, _, changed = smart.update(_sensor(tc=60.0), 1.0)
        writes.append(changed)
    assert writes.count(True) <= 3, "deadband пропустил слишком много записей"


# --------------------------------------------------------------------------- #
# Одноканальный PWM
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_hwmon(tmp_path, monkeypatch):
    """Временный hp-hwmon: только канал 0, как у Omen Space hp-wmi."""
    (tmp_path / "name").write_text("hp\n")
    (tmp_path / "pwm1").write_text("0\n")
    (tmp_path / "pwm1_enable").write_text("1\n")
    (tmp_path / "fan1_input").write_text("0\n")
    (tmp_path / "fan2_input").write_text("0\n")
    monkeypatch.setattr(F, "find_hwmon", lambda chip, need=None: str(tmp_path))
    return tmp_path


def _fans(fake_hwmon) -> F.Fans:
    return F.Fans(_preset())


def test_single_channel_detected(fake_hwmon):
    fans = _fans(fake_hwmon)
    assert fans.shared_pwm is True
    assert fans.channels == 1
    assert fans.gpu_pwm_out is None


def test_single_channel_write_uses_max(fake_hwmon):
    """Один канал: пишется max(p1, p2), иначе требование GPU молча теряется."""
    fans = _fans(fake_hwmon)
    assert fans.set_pwm(40, 200) is None
    assert (fake_hwmon / "pwm1").read_text().strip() == "200"
    assert fans.set_pwm(210, 40) is None
    assert (fake_hwmon / "pwm1").read_text().strip() == "210"


def test_missing_attribute_is_not_a_rights_error(fake_hwmon):
    """Отсутствующий атрибут — не «нет прав: нужен root»."""
    fans = _fans(fake_hwmon)
    err = fans._w("pwm2", 100)
    assert err is not None
    assert "прав" not in err, "ложная ошибка про права: %s" % err
    assert "pwm2" in err


def test_read_reports_shared_channel(fake_hwmon):
    fans = _fans(fake_hwmon)
    (fake_hwmon / "pwm1").write_text("150\n")
    snap = fans.read()
    assert snap["pwm_shared"] is True
    assert snap["pwm1"] == snap["pwm2"] == 150


def test_writable_requires_existing_attrs(fake_hwmon):
    fans = _fans(fake_hwmon)
    os.chmod(str(fake_hwmon / "pwm1"), 0o444)
    os.chmod(str(fake_hwmon / "pwm1_enable"), 0o444)
    if os.geteuid() != 0:
        assert fans.writable is False, "атрибуты без записи — writable обязан быть False"
