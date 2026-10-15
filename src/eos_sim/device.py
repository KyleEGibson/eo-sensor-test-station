"""Behavioral model of the EOS-100 electro-optical sensor.

This is the device under test (DUT). It stands in for real hardware so the test
station can be developed and exercised without a lab. The model is simple but
physically plausible:

* the detector cooler follows a first-order exponential toward its setpoint,
* the two-axis gimbal slews at a fixed rate and reports encoder noise,
* the imager's output is linear in gain x exposure until the 12-bit ADC saturates,
* current draw rises while the cooler pulls down and while the gimbal moves.

All timing runs on a simulated clock that can be sped up (``speed``) so the full
test suite finishes in seconds. The command set is described in
docs/interface_control_document.md.
"""

from __future__ import annotations

import math
import random
import threading
import time
import zlib
from collections import deque
from typing import Callable

from .faults import BIT_FLAGS, Fault

MANUFACTURER = "GIBSON-SIM"
MODEL = "EOS-100"
FIRMWARE_VERSION = "2.4.1"

BOOT_TIME_S = 2.0

AMBIENT_C = 25.0
COOLER_SETPOINT_C = -40.0
COOLER_TAU_S = 2.0
COOLER_READY_BAND_C = 0.5
TEMP_DRIFT_C_PER_S = 0.4
TEMP_DRIFT_ONSET_S = 2.0  # cooler holds setpoint this long before losing regulation

AZ_LIMITS = (-170.0, 170.0)
EL_LIMITS = (-30.0, 90.0)
SLEW_RATE_DPS = 60.0
ENCODER_NOISE_DEG = 0.02
STALL_FRACTION = 0.4

BUS_VOLTAGE_V = 28.0
SAG_VOLTAGE_V = 24.2
BASE_CURRENT_A = 1.1
COOLER_CURRENT_A = 0.9
GIMBAL_CURRENT_A = 1.4

GAIN_LIMITS = (1, 16)
EXPOSURE_LIMITS_MS = (0.1, 100.0)
ADC_MAX = 4095
DARK_LEVEL = 64.0
COUNTS_PER_GAIN_MS = 3.0
NORMAL_DEAD_PIXELS = 2
FAULT_DEAD_PIXELS = 147

ERROR_QUEUE_SIZE = 10


class ScpiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"{code},{message}")
        self.code = code
        self.message = message


UNDEFINED_HEADER = (-113, "Undefined header")
MISSING_PARAMETER = (-109, "Missing parameter")
DATA_TYPE_ERROR = (-104, "Data type error")
OUT_OF_RANGE = (-222, "Data out of range")
NOT_POWERED = (-200, "Execution error; not powered")
NOT_READY = (-201, "Execution error; not ready")
QUEUE_OVERFLOW = (-350, "Queue overflow")


def checksum(payload: str) -> str:
    value = 0
    for byte in payload.encode("ascii"):
        value ^= byte
    return f"{value:02X}"


class _Axis:
    """One gimbal axis slewing at a constant rate toward its target."""

    def __init__(self) -> None:
        self.start = 0.0
        self.target = 0.0
        self.t0 = 0.0

    def command(self, target: float, now: float, stalled: bool = False) -> None:
        self.start = self.position(now, stalled)
        self.target = target
        self.t0 = now

    def position(self, now: float, stalled: bool = False) -> float:
        travel = self.target - self.start
        reach = SLEW_RATE_DPS * (now - self.t0)
        if stalled:
            reach = min(reach, abs(travel) * STALL_FRACTION)
        if reach >= abs(travel):
            return self.target
        return self.start + math.copysign(reach, travel)

    def moving(self, now: float, stalled: bool = False) -> bool:
        return self.position(now, stalled) != self.target


class Device:
    """Thread-safe model of one EOS-100 unit."""

    def __init__(
        self,
        serial: str = "000123",
        speed: float = 1.0,
        seed: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.serial = serial
        self.speed = speed
        self._wall_clock = clock or time.monotonic
        self._t_origin = self._wall_clock()
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self.faults: set[Fault] = set()
        self._responses = 0
        self._powered_at: float | None = None
        self._errors: deque[tuple[int, str]] = deque()
        self._az = _Axis()
        self._el = _Axis()
        self._gain = 1
        self._exposure_ms = 10.0
        self._frame_id = 0
        self._commands = {
            "*IDN?": self._idn,
            "*RST": self._rst,
            "*TST?": self._tst,
            "SYST:POW": self._set_power,
            "SYST:POW?": self._get_power,
            "SYST:STAT?": self._state,
            "SYST:ERR?": self._next_error,
            "MEAS:VOLT?": self._voltage,
            "MEAS:CURR?": self._current,
            "MEAS:TEMP?": self._temperature,
            "COOL:STAT?": self._cooler_state,
            "GIMB:AZ": self._set_azimuth,
            "GIMB:EL": self._set_elevation,
            "GIMB:POS?": self._position,
            "GIMB:STAT?": self._gimbal_state,
            "GIMB:HOME": self._home,
            "IMG:GAIN": self._set_gain,
            "IMG:GAIN?": lambda arg: str(self._gain),
            "IMG:EXP": self._set_exposure,
            "IMG:EXP?": lambda arg: f"{self._exposure_ms:.1f}",
            "IMG:CAPT?": self._capture,
            "SIM:FAULT": self._inject_fault,
            "SIM:FAULT?": lambda arg: ",".join(sorted(f.value for f in self.faults)) or "NONE",
            "SIM:FAULT:CLR": self._clear_faults,
        }
        # Commands that work regardless of power state.
        self._always_available = {
            "*IDN?", "*RST", "SYST:POW", "SYST:POW?", "SYST:STAT?", "SYST:ERR?",
            "SIM:FAULT", "SIM:FAULT?", "SIM:FAULT:CLR",
        }

    # ------------------------------------------------------------------ public

    def now(self) -> float:
        """Simulated seconds since the device was created."""
        return (self._wall_clock() - self._t_origin) * self.speed

    def handle(self, line: str) -> str | None:
        """Execute one command line and return the framed response.

        Returns None when a communication fault swallows the response.
        """
        with self._lock:
            payload = self._execute(line.strip())
            self._responses += 1
            if Fault.COMM_DROP in self.faults and self._responses % 3 == 0:
                return None
            framed = f"{payload}*{checksum(payload)}"
            if Fault.COMM_CORRUPT in self.faults and self._responses % 3 == 0:
                framed = chr(ord(framed[0]) ^ 0x20) + framed[1:]
            return framed

    # ---------------------------------------------------------------- dispatch

    def _execute(self, line: str) -> str:
        header, _, arg = line.partition(" ")
        header = header.upper()
        try:
            handler = self._commands.get(header)
            if handler is None:
                raise ScpiError(*UNDEFINED_HEADER)
            if header not in self._always_available:
                state = self._power_state()
                if state == "OFF":
                    raise ScpiError(*NOT_POWERED)
                if state == "BOOTING":
                    raise ScpiError(*NOT_READY)
            result = handler(arg.strip())
            return "OK" if result is None else result
        except ScpiError as err:
            self._push_error(err.code, err.message)
            return f"ERR {err.code}"

    def _push_error(self, code: int, message: str) -> None:
        if len(self._errors) >= ERROR_QUEUE_SIZE:
            self._errors[-1] = QUEUE_OVERFLOW
            return
        self._errors.append((code, message))

    # ------------------------------------------------------------------- power

    def _power_state(self) -> str:
        if self._powered_at is None:
            return "OFF"
        if self.now() - self._powered_at < BOOT_TIME_S:
            return "BOOTING"
        return "READY"

    def _set_power(self, arg: str) -> None:
        arg = arg.upper()
        if arg == "ON":
            if self._powered_at is None:
                self._powered_at = self.now()
        elif arg == "OFF":
            self._powered_at = None
            self._reset_state()
        elif not arg:
            raise ScpiError(*MISSING_PARAMETER)
        else:
            raise ScpiError(*DATA_TYPE_ERROR)

    def _get_power(self, arg: str) -> str:
        return "OFF" if self._powered_at is None else "ON"

    def _state(self, arg: str) -> str:
        return self._power_state()

    def _reset_state(self) -> None:
        now = self.now()
        self._az = _Axis()
        self._el = _Axis()
        self._az.t0 = self._el.t0 = now
        self._gain = 1
        self._exposure_ms = 10.0

    def _rst(self, arg: str) -> None:
        now = self.now()
        stalled = Fault.GIMBAL_STALL in self.faults
        self._az.command(0.0, now, stalled)
        self._el.command(0.0, now)
        self._gain = 1
        self._exposure_ms = 10.0
        self._errors.clear()

    def _voltage(self, arg: str) -> str:
        nominal = SAG_VOLTAGE_V if Fault.VOLT_SAG in self.faults else BUS_VOLTAGE_V
        return f"{nominal + self._rng.gauss(0, 0.03):.2f}"

    def _current(self, arg: str) -> str:
        now = self.now()
        amps = BASE_CURRENT_A
        if self._cooler_pulling_down(now):
            amps += COOLER_CURRENT_A
        stalled = Fault.GIMBAL_STALL in self.faults
        if self._az.moving(now, stalled) or self._el.moving(now):
            amps += GIMBAL_CURRENT_A
        return f"{amps + self._rng.gauss(0, 0.02):.2f}"

    def _tst(self, arg: str) -> str:
        result = 0
        for fault in self.faults:
            result |= BIT_FLAGS.get(fault, 0)
        return str(result)

    # ----------------------------------------------------------------- thermal

    def _cooler_ready_after(self) -> float:
        """Seconds after power-on at which the cooler enters its ready band."""
        span = AMBIENT_C - COOLER_SETPOINT_C
        return COOLER_TAU_S * math.log(span / COOLER_READY_BAND_C)

    def _cooler_pulling_down(self, now: float) -> bool:
        if self._powered_at is None:
            return False
        return now - self._powered_at < self._cooler_ready_after()

    def _detector_temp(self, now: float) -> float:
        if self._powered_at is None:
            return AMBIENT_C
        elapsed = now - self._powered_at
        span = AMBIENT_C - COOLER_SETPOINT_C
        temp = COOLER_SETPOINT_C + span * math.exp(-elapsed / COOLER_TAU_S)
        if Fault.TEMP_DRIFT in self.faults:
            temp += TEMP_DRIFT_C_PER_S * max(0.0, elapsed - self._cooler_ready_after() - TEMP_DRIFT_ONSET_S)
        return temp

    def _temperature(self, arg: str) -> str:
        return f"{self._detector_temp(self.now()) + self._rng.gauss(0, 0.05):.2f}"

    def _cooler_state(self, arg: str) -> str:
        temp = self._detector_temp(self.now())
        return "READY" if abs(temp - COOLER_SETPOINT_C) <= COOLER_READY_BAND_C else "COOLING"

    # ------------------------------------------------------------------ gimbal

    @staticmethod
    def _parse_float(arg: str) -> float:
        if not arg:
            raise ScpiError(*MISSING_PARAMETER)
        try:
            return float(arg)
        except ValueError:
            raise ScpiError(*DATA_TYPE_ERROR) from None

    def _set_azimuth(self, arg: str) -> None:
        target = self._parse_float(arg)
        if not AZ_LIMITS[0] <= target <= AZ_LIMITS[1]:
            raise ScpiError(*OUT_OF_RANGE)
        self._az.command(target, self.now(), Fault.GIMBAL_STALL in self.faults)

    def _set_elevation(self, arg: str) -> None:
        target = self._parse_float(arg)
        if not EL_LIMITS[0] <= target <= EL_LIMITS[1]:
            raise ScpiError(*OUT_OF_RANGE)
        self._el.command(target, self.now())

    def _home(self, arg: str) -> None:
        now = self.now()
        self._az.command(0.0, now, Fault.GIMBAL_STALL in self.faults)
        self._el.command(0.0, now)

    def _position(self, arg: str) -> str:
        now = self.now()
        az = self._az.position(now, Fault.GIMBAL_STALL in self.faults)
        el = self._el.position(now)
        az += self._rng.uniform(-ENCODER_NOISE_DEG, ENCODER_NOISE_DEG)
        el += self._rng.uniform(-ENCODER_NOISE_DEG, ENCODER_NOISE_DEG)
        return f"{az:.3f},{el:.3f}"

    def _gimbal_state(self, arg: str) -> str:
        now = self.now()
        stalled = Fault.GIMBAL_STALL in self.faults
        return "MOVING" if self._az.moving(now, stalled) or self._el.moving(now) else "IDLE"

    # ------------------------------------------------------------------ imager

    def _set_gain(self, arg: str) -> None:
        value = self._parse_float(arg)
        if value != int(value) or not GAIN_LIMITS[0] <= value <= GAIN_LIMITS[1]:
            raise ScpiError(*OUT_OF_RANGE)
        self._gain = int(value)

    def _set_exposure(self, arg: str) -> None:
        value = self._parse_float(arg)
        if not EXPOSURE_LIMITS_MS[0] <= value <= EXPOSURE_LIMITS_MS[1]:
            raise ScpiError(*OUT_OF_RANGE)
        self._exposure_ms = value

    def _capture(self, arg: str) -> str:
        self._frame_id += 1
        signal = DARK_LEVEL + COUNTS_PER_GAIN_MS * self._gain * self._exposure_ms
        mean = min(ADC_MAX, signal + self._rng.gauss(0, 0.5))
        std = 0.5 * math.sqrt(mean) + 1.5
        dead = FAULT_DEAD_PIXELS if Fault.DEAD_PIXELS in self.faults else NORMAL_DEAD_PIXELS
        body = f"{self._frame_id},{mean:.2f},{std:.2f},{dead}"
        return f"{body},{zlib.crc32(body.encode('ascii')):08X}"

    # ----------------------------------------------------------- sim controls

    def _inject_fault(self, arg: str) -> None:
        try:
            self.faults.add(Fault(arg.upper()))
        except ValueError:
            raise ScpiError(*DATA_TYPE_ERROR) from None

    def _clear_faults(self, arg: str) -> None:
        self.faults.clear()

    def _idn(self, arg: str) -> str:
        return f"{MANUFACTURER},{MODEL},SN{self.serial},{FIRMWARE_VERSION}"

    def _next_error(self, arg: str) -> str:
        if not self._errors:
            return '0,"No error"'
        code, message = self._errors.popleft()
        return f'{code},"{message}"'
