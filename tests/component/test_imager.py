"""Imager parameter ranges, image quality and data integrity."""

import pytest

from test_station import limits
from test_station.driver import DeviceError


@pytest.mark.req("SYS-030")
@pytest.mark.parametrize("gain", [1, 8, 16])
def test_valid_gain_accepted(sensor, gain):
    sensor.set_gain(gain)
    assert sensor.query("IMG:GAIN?") == str(gain)


@pytest.mark.req("SYS-030")
@pytest.mark.parametrize("exposure", [0.1, 33.3, 100.0])
def test_valid_exposure_accepted(sensor, exposure):
    sensor.set_exposure(exposure)
    assert float(sensor.query("IMG:EXP?")) == pytest.approx(exposure)


@pytest.mark.req("SYS-030")
@pytest.mark.parametrize("command", ["IMG:GAIN 0", "IMG:GAIN 17", "IMG:GAIN 2.5", "IMG:EXP 0.05", "IMG:EXP 100.1"])
def test_out_of_range_imager_settings_rejected(sensor, command):
    with pytest.raises(DeviceError) as err:
        sensor.write(command)
    assert err.value.code == limits.OUT_OF_RANGE


@pytest.mark.req("SYS-031")
def test_dead_pixel_count(sensor, measure):
    frames = [sensor.capture() for _ in range(5)]
    measure("worst-case dead pixels (5 frames)", max(f.dead_pixels for f in frames),
            high=limits.DEAD_PIXELS_MAX, units="px")


@pytest.mark.req("SYS-033")
def test_frame_crc(sensor, measure):
    frames = [sensor.capture() for _ in range(10)]
    measure("frames with bad CRC", sum(not f.crc_ok for f in frames), high=0)
    assert len({f.frame_id for f in frames}) == 10, "frame IDs must be unique"


def r_squared(xs, ys):
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    return 1 - ss_res / ss_tot, slope


@pytest.mark.req("SYS-032")
def test_exposure_linearity(sensor, measure):
    sensor.set_gain(4)
    exposures = [5, 10, 20, 40, 60, 80]
    means = []
    for exposure in exposures:
        sensor.set_exposure(exposure)
        means.append(sensor.capture().mean)
    r2, slope = r_squared(exposures, means)
    measure("response slope", slope, low=0, units="counts/ms")
    measure("linearity R^2", r2, low=limits.LINEARITY_R2_MIN)
