"""Identification and command-interface tests."""

import re

import pytest

from test_station import limits
from test_station.driver import DeviceError, checksum


@pytest.mark.req("SYS-001")
def test_identity_fields(sensor):
    identity = sensor.identify()
    assert identity.manufacturer == "GIBSON-SIM"
    assert identity.model == "EOS-100"
    assert re.fullmatch(r"SN\d{6}", identity.serial), identity.serial
    assert re.fullmatch(r"\d+\.\d+\.\d+", identity.firmware), identity.firmware


@pytest.mark.req("SYS-041")
@pytest.mark.parametrize("command", ["*IDN?", "SYST:STAT?", "MEAS:VOLT?", "GIMB:POS?", "BOGUS"])
def test_every_response_carries_checksum(sensor, command):
    try:
        sensor.transact(command)
    except DeviceError:
        pass  # error responses must be framed too
    raw = sensor.comm_log[-1][2]
    payload, sep, check = raw.rpartition("*")
    assert sep == "*", f"no checksum in {raw!r}"
    assert check == checksum(payload)


@pytest.mark.req("SYS-040")
def test_error_queue_is_fifo_and_clears(sensor):
    with pytest.raises(DeviceError) as first:
        sensor.write("GIMB:AZ 999")
    with pytest.raises(DeviceError) as second:
        sensor.write("NOT:A:COMMAND")
    assert first.value.code == limits.OUT_OF_RANGE
    assert sensor.errors() == [(-222, "Data out of range"), (-113, "Undefined header")]
    assert sensor.errors() == []
    assert sensor.query("SYST:ERR?") == '0,"No error"'
