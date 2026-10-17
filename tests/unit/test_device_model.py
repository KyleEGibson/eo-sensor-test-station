"""Simulator model tests with a fake clock. Not traced to the SRS since they
test the simulator, not the sensor."""

import math
import zlib

import pytest

from eos_sim import Device, Fault
from eos_sim import device as model


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def dev(clock):
    return Device(clock=clock)


def payload(response: str) -> str:
    body, _, check = response.rpartition("*")
    assert check == model.checksum(body)
    return body


def powered(dev, clock):
    payload(dev.handle("SYST:POW ON"))
    clock.t += model.BOOT_TIME_S
    return dev


def test_boot_sequence(dev, clock):
    assert payload(dev.handle("SYST:STAT?")) == "OFF"
    dev.handle("SYST:POW ON")
    assert payload(dev.handle("SYST:STAT?")) == "BOOTING"
    clock.t += model.BOOT_TIME_S
    assert payload(dev.handle("SYST:STAT?")) == "READY"


def test_commands_gated_by_power_state(dev, clock):
    assert payload(dev.handle("MEAS:VOLT?")) == "ERR -200"
    dev.handle("SYST:POW ON")
    assert payload(dev.handle("MEAS:VOLT?")) == "ERR -201"


def test_unknown_command_is_queued_as_error(dev):
    assert payload(dev.handle("FOO:BAR?")) == "ERR -113"
    assert payload(dev.handle("SYST:ERR?")) == '-113,"Undefined header"'
    assert payload(dev.handle("SYST:ERR?")) == '0,"No error"'


def test_error_queue_overflow_replaces_last_entry(dev):
    for _ in range(model.ERROR_QUEUE_SIZE + 3):
        dev.handle("BAD")
    errors = [payload(dev.handle("SYST:ERR?")) for _ in range(model.ERROR_QUEUE_SIZE)]
    assert errors[-1].startswith("-350")


def test_cooler_follows_exponential(dev, clock):
    dev.handle("SYST:POW ON")
    clock.t += model.COOLER_TAU_S
    expected = model.COOLER_SETPOINT_C + (model.AMBIENT_C - model.COOLER_SETPOINT_C) / math.e
    assert float(payload(dev.handle("MEAS:TEMP?"))) == pytest.approx(expected, abs=0.3)


def test_gimbal_slews_at_rated_speed(dev, clock):
    powered(dev, clock)
    dev.handle("GIMB:AZ 60")
    clock.t += 0.5
    az, _ = map(float, payload(dev.handle("GIMB:POS?")).split(","))
    assert az == pytest.approx(30.0, abs=0.05)
    assert payload(dev.handle("GIMB:STAT?")) == "MOVING"
    clock.t += 0.5
    assert payload(dev.handle("GIMB:STAT?")) == "IDLE"


def test_gimbal_stall_stops_short(dev, clock):
    powered(dev, clock)
    dev.faults.add(Fault.GIMBAL_STALL)
    dev.handle("GIMB:AZ 100")
    clock.t += 10
    az, _ = map(float, payload(dev.handle("GIMB:POS?")).split(","))
    assert az == pytest.approx(100 * model.STALL_FRACTION, abs=0.05)
    assert payload(dev.handle("GIMB:STAT?")) == "MOVING"


def test_frame_crc_matches_body(dev, clock):
    powered(dev, clock)
    fields = payload(dev.handle("IMG:CAPT?")).split(",")
    body = ",".join(fields[:4])
    assert int(fields[4], 16) == zlib.crc32(body.encode("ascii"))


def test_imager_saturates_at_adc_max(dev, clock):
    powered(dev, clock)
    dev.handle("IMG:GAIN 16")
    dev.handle("IMG:EXP 100")
    mean = float(payload(dev.handle("IMG:CAPT?")).split(",")[1])
    assert mean == model.ADC_MAX


def test_comm_drop_loses_every_third_response(dev):
    dev.faults.add(Fault.COMM_DROP)
    responses = [dev.handle("*IDN?") for _ in range(6)]
    assert [r is None for r in responses] == [False, False, True, False, False, True]


def test_comm_corrupt_breaks_checksum(dev):
    dev.faults.add(Fault.COMM_CORRUPT)
    responses = [dev.handle("*IDN?") for _ in range(3)]
    body, _, check = responses[2].rpartition("*")
    assert model.checksum(body) != check


def test_bit_reports_detectable_faults_only(dev, clock):
    powered(dev, clock)
    dev.faults.update({Fault.GIMBAL_STALL, Fault.TEMP_DRIFT})
    assert payload(dev.handle("*TST?")) == "2"
