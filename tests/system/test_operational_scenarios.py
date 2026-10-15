"""System-level tests: end-to-end scenarios that exercise every subsystem together."""

import time

import pytest

from test_station import limits

pytestmark = pytest.mark.system

SCAN_PATTERN = [(-60, 10), (-30, 20), (0, 30), (30, 20), (60, 10)]


@pytest.mark.req("SYS-002", "SYS-003", "SYS-010", "SYS-020", "SYS-021", "SYS-031", "SYS-033")
def test_cold_start_to_imaging_mission(sensor, measure):
    """Cold start, wait for the cooler, then run a five-point scan with a capture at each point."""
    sensor.power_off()
    sensor.power_on()
    powered_at = time.monotonic()
    measure("time to READY", sensor.wait_until_ready(timeout_s=10.0), high=limits.BOOT_TIME_MAX_S, units="s")
    measure("BIT result", sensor.self_test(), low=0, high=0)
    sensor.wait_cooler_ready(timeout_s=limits.COOLDOWN_MAX_S * 2)
    measure("time to cooler READY", (time.monotonic() - powered_at) * sensor.time_scale,
            high=limits.COOLDOWN_MAX_S, units="s")

    sensor.set_gain(4)
    sensor.set_exposure(20)
    tol = limits.POINTING_TOLERANCE_DEG
    for index, (azimuth, elevation) in enumerate(SCAN_PATTERN, start=1):
        sensor.point(azimuth, elevation)
        sensor.wait_gimbal_idle(timeout_s=10.0)
        az, el = sensor.position()
        frame = sensor.capture()
        measure(f"point {index} azimuth error", az - azimuth, low=-tol, high=tol, units="deg")
        measure(f"point {index} elevation error", el - elevation, low=-tol, high=tol, units="deg")
        measure(f"point {index} dead pixels", frame.dead_pixels, high=limits.DEAD_PIXELS_MAX, units="px")
        measure(f"point {index} frame CRC ok", int(frame.crc_ok), low=1, high=1)


@pytest.mark.req("SYS-006", "SYS-022")
def test_current_stays_in_budget_while_scanning_and_imaging(sensor, measure):
    peak = 0.0
    for azimuth, elevation in [(-150, 0), (150, 85), (0, -25), (0, 0)]:
        sensor.point(azimuth, elevation)
        while sensor.query("GIMB:STAT?") == "MOVING":
            peak = max(peak, sensor.current())
            sensor.capture()
    measure("peak current while scanning", peak, high=limits.CURRENT_MAX_A, units="A")


@pytest.mark.req("SYS-007")
def test_power_cycle_restores_defaults(sensor, measure):
    sensor.set_gain(12)
    sensor.set_exposure(55)
    sensor.point(100, 45)
    sensor.wait_gimbal_idle(timeout_s=10.0)

    sensor.power_off()
    sensor.power_on()
    sensor.wait_until_ready(timeout_s=10.0)
    az, el = sensor.position()
    tol = limits.POINTING_TOLERANCE_DEG
    measure("azimuth after power cycle", az, low=-tol, high=tol, units="deg")
    measure("elevation after power cycle", el, low=-tol, high=tol, units="deg")
    measure("gain after power cycle", int(sensor.query("IMG:GAIN?")), low=1, high=1)
    measure("exposure after power cycle", float(sensor.query("IMG:EXP?")), low=10.0, high=10.0, units="ms")
