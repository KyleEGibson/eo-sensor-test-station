"""Detector cooler performance."""

import time

import pytest

from test_station import limits


@pytest.fixture
def cold_start(sensor):
    """Power-cycle so the cooler starts from ambient; return power-on time.

    COOL:STAT? is rejected while booting (SYS-004), so wait for READY before
    polling the cooler. Cooldown time is still measured from power-on.
    """
    sensor.power_off()
    sensor.power_on()
    powered_at = time.monotonic()
    sensor.wait_until_ready(timeout_s=10.0)
    return powered_at


@pytest.mark.timing
@pytest.mark.req("SYS-010")
def test_cooldown_time_and_setpoint(sensor, cold_start, measure):
    sensor.wait_cooler_ready(timeout_s=limits.COOLDOWN_MAX_S * 2)
    elapsed = (time.monotonic() - cold_start) * sensor.time_scale
    low, high = limits.cooler_band()
    measure("cooldown time", elapsed, high=limits.COOLDOWN_MAX_S, units="s")
    measure("detector temperature at READY", sensor.temperature(), low=low, high=high, units="C")


@pytest.mark.timing
@pytest.mark.req("SYS-011")
def test_temperature_stability(sensor, cold_start, measure):
    sensor.wait_cooler_ready(timeout_s=limits.COOLDOWN_MAX_S * 2)
    samples = []
    end = time.monotonic() + limits.STABILITY_WINDOW_S / sensor.time_scale
    while time.monotonic() < end:
        samples.append(sensor.temperature())
        sensor.sleep(0.5)
    low, high = limits.cooler_band()
    measure("samples taken", len(samples), low=10)
    measure("minimum temperature", min(samples), low=low, high=high, units="C")
    measure("maximum temperature", max(samples), low=low, high=high, units="C")
