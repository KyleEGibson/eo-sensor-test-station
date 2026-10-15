"""Gimbal pointing accuracy, slew rate and travel limits."""

import time

import pytest

from test_station import limits
from test_station.driver import DeviceError

TOL = limits.POINTING_TOLERANCE_DEG
SETTLE_TIMEOUT_S = 10.0

POINTS = [(0, 0), (45, 10), (-120, 60), (169.9, -29.9), (-169.9, 89.9)]


@pytest.mark.req("SYS-020", "SYS-021")
@pytest.mark.parametrize("azimuth, elevation", POINTS, ids=[f"az{a}_el{e}" for a, e in POINTS])
def test_pointing_accuracy(sensor, measure, azimuth, elevation):
    sensor.point(azimuth, elevation)
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    az, el = sensor.position()
    measure("azimuth error", az - azimuth, low=-TOL, high=TOL, units="deg")
    measure("elevation error", el - elevation, low=-TOL, high=TOL, units="deg")


@pytest.mark.req("SYS-022")
def test_slew_time_90_degrees(sensor, measure):
    sensor.home()
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    start = time.monotonic()
    sensor.write("GIMB:AZ 90")
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    elapsed = (time.monotonic() - start) * sensor.time_scale
    measure("90 deg azimuth slew time", elapsed, high=limits.SLEW_90_MAX_S, units="s")


BAD_COMMANDS = ["GIMB:AZ 170.1", "GIMB:AZ -180", "GIMB:EL -30.5", "GIMB:EL 91"]


@pytest.mark.req("SYS-023")
@pytest.mark.parametrize("command", BAD_COMMANDS)
def test_travel_limits_rejected(sensor, command):
    sensor.point(10, 10)
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    with pytest.raises(DeviceError) as err:
        sensor.write(command)
    assert err.value.code == limits.OUT_OF_RANGE
    az, el = sensor.position()
    assert az == pytest.approx(10, abs=TOL) and el == pytest.approx(10, abs=TOL), "gimbal moved"


@pytest.mark.req("SYS-024")
@pytest.mark.parametrize("command", ["GIMB:HOME", "*RST"])
def test_return_to_home(sensor, measure, command):
    sensor.point(-60, 45)
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    sensor.write(command)
    sensor.wait_gimbal_idle(SETTLE_TIMEOUT_S)
    az, el = sensor.position()
    measure("azimuth after home", az, low=-TOL, high=TOL, units="deg")
    measure("elevation after home", el, low=-TOL, high=TOL, units="deg")
