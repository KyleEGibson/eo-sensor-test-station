"""Power, startup and built-in test."""

import pytest

from test_station import limits
from test_station.driver import DeviceError


@pytest.fixture
def powered_off(sensor):
    sensor.power_off()
    assert sensor.state() == "OFF"
    return sensor


@pytest.mark.timing
@pytest.mark.req("SYS-002")
def test_boot_time(powered_off, measure):
    powered_off.power_on()
    boot_s = powered_off.wait_until_ready(timeout_s=limits.BOOT_TIME_MAX_S * 2)
    measure("time to READY", boot_s, high=limits.BOOT_TIME_MAX_S, units="s")


@pytest.mark.timing
@pytest.mark.req("SYS-004")
def test_commands_rejected_while_off_and_booting(powered_off):
    with pytest.raises(DeviceError) as off:
        powered_off.voltage()
    assert off.value.code == limits.NOT_POWERED

    powered_off.power_on()
    with pytest.raises(DeviceError) as booting:
        powered_off.voltage()
    assert booting.value.code == limits.NOT_READY


@pytest.mark.req("SYS-003")
def test_built_in_self_test_passes(sensor, measure):
    measure("BIT result", sensor.self_test(), low=0, high=0)


@pytest.mark.req("SYS-005")
def test_bus_voltage(sensor, measure):
    readings = [sensor.voltage() for _ in range(5)]
    low, high = limits.BUS_VOLTAGE_V
    measure("bus voltage (min of 5)", min(readings), low=low, high=high, units="V")
    measure("bus voltage (max of 5)", max(readings), low=low, high=high, units="V")


@pytest.mark.req("SYS-006")
def test_peak_current_during_cooldown_and_slew(powered_off, measure):
    """Worst case: cooler pulling down while the gimbal slews."""
    powered_off.power_on()
    powered_off.wait_until_ready(timeout_s=10.0)
    powered_off.point(150, 80)
    peak = max(powered_off.current() for _ in range(20))
    measure("peak input current", peak, high=limits.CURRENT_MAX_A, units="A")
