"""Verify that the station's checks catch each injectable hardware fault (TS-005).

A test suite that never fails is not evidence of anything. Each test here
injects one fault and confirms the corresponding acceptance check would flag
it, using the same limits as the acceptance tests.
"""

import pytest

from test_station import limits
from test_station.results import Measurement


def out_of_limits(name, value, low=None, high=None):
    return not Measurement(name, value, low, high).passed


@pytest.mark.req("TS-005")
def test_detects_voltage_sag(sensor, inject):
    inject("VOLT_SAG")
    assert out_of_limits("bus voltage", sensor.voltage(), *limits.BUS_VOLTAGE_V)
    assert sensor.self_test() & 0b1000, "BIT should flag the power fault"


@pytest.mark.req("TS-005")
def test_detects_gimbal_stall(sensor, inject):
    inject("GIMBAL_STALL")
    sensor.point(90, 0)
    with pytest.raises(TimeoutError):
        sensor.wait_gimbal_idle(timeout_s=5.0)
    az, _ = sensor.position()
    assert out_of_limits("azimuth error", az - 90, -limits.POINTING_TOLERANCE_DEG, limits.POINTING_TOLERANCE_DEG)
    assert sensor.self_test() & 0b0010, "BIT should flag the gimbal fault"


@pytest.mark.req("TS-005")
def test_detects_dead_pixels(sensor, inject):
    inject("DEAD_PIXELS")
    assert out_of_limits("dead pixels", sensor.capture().dead_pixels, high=limits.DEAD_PIXELS_MAX)


@pytest.mark.req("TS-005")
def test_detects_temperature_drift_that_bit_misses(sensor, inject):
    """The sensor's own BIT does not monitor cooler regulation; only the
    external stability test catches this fault."""
    sensor.power_off()
    sensor.power_on()
    sensor.wait_until_ready(timeout_s=10.0)
    inject("TEMP_DRIFT")
    sensor.wait_cooler_ready(timeout_s=limits.COOLDOWN_MAX_S * 2)
    sensor.sleep(limits.STABILITY_WINDOW_S)
    assert out_of_limits("detector temperature", sensor.temperature(), *limits.cooler_band())
    assert sensor.self_test() == 0
