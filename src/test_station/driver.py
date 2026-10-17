"""EOS-100 driver, written from the ICD separately from the simulator.

The URL can be a serial port (COM3, /dev/ttyUSB0) or socket://host:port.
Durations are in device seconds; time_scale is the simulator speed-up (1.0 on
real hardware).
"""

from __future__ import annotations

import time
import zlib
from dataclasses import dataclass

import serial


class CommError(Exception):
    """The sensor did not return a valid response."""


class DeviceError(Exception):
    """The sensor executed the command and reported an error code."""

    def __init__(self, code: int, command: str) -> None:
        super().__init__(f"{command!r} rejected with error {code}")
        self.code = code
        self.command = command


@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial: str
    firmware: str


@dataclass(frozen=True)
class Frame:
    frame_id: int
    mean: float
    std: float
    dead_pixels: int
    crc: int
    body: str

    @property
    def crc_ok(self) -> bool:
        return zlib.crc32(self.body.encode("ascii")) == self.crc


def checksum(payload: str) -> str:
    value = 0
    for byte in payload.encode("ascii"):
        value ^= byte
    return f"{value:02X}"


def unframe(raw: bytes) -> str:
    if not raw.endswith(b"\n"):
        raise CommError("timed out waiting for response")
    try:
        line = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        raise CommError(f"non-ASCII response {raw!r}") from None
    payload, sep, check = line.rpartition("*")
    if not sep:
        raise CommError(f"response missing checksum: {line!r}")
    if checksum(payload) != check.upper():
        raise CommError(f"checksum mismatch in {line!r}")
    return payload


class EOSensor:
    def __init__(
        self,
        url: str,
        timeout: float = 0.2,
        retries: int = 2,
        time_scale: float = 1.0,
        poll_interval: float = 0.01,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self.time_scale = time_scale
        self.poll_interval = poll_interval
        self.retries_used = 0
        self.comm_log: list[tuple[float, str, str, int]] = []
        self._port: serial.SerialBase | None = None

    # connection
    def open(self) -> "EOSensor":
        self._port = serial.serial_for_url(self.url, timeout=self.timeout)
        return self

    def close(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None

    def __enter__(self) -> "EOSensor":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # transport
    def transact(self, command: str) -> str:
        # retries on timeout/bad checksum; ERR <code> is a real answer so no retry
        if self._port is None:
            raise CommError("port is not open")
        failure: CommError | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                self.retries_used += 1
                self._port.reset_input_buffer()
            self._port.write((command + "\n").encode("ascii"))
            raw = self._port.read_until(b"\n")
            self.comm_log.append((time.time(), command, raw.decode("ascii", "replace").strip(), attempt))
            try:
                payload = unframe(raw)
            except CommError as exc:
                failure = exc
                continue
            if payload.startswith("ERR "):
                raise DeviceError(int(payload[4:]), command)
            return payload
        raise CommError(f"{command!r} failed after {self.retries + 1} attempts: {failure}")

    def query(self, command: str) -> str:
        return self.transact(command)

    def write(self, command: str) -> None:
        response = self.transact(command)
        if response != "OK":
            raise CommError(f"{command!r} expected OK, got {response!r}")

    def _poll(self, command: str, expected: str, timeout_s: float) -> float:
        start = time.monotonic()
        deadline = start + timeout_s / self.time_scale
        while True:
            if self.query(command) == expected:
                return (time.monotonic() - start) * self.time_scale
            if time.monotonic() > deadline:
                raise TimeoutError(f"{command} did not return {expected} within {timeout_s} s")
            time.sleep(self.poll_interval)

    def sleep(self, device_seconds: float) -> None:
        time.sleep(device_seconds / self.time_scale)

    # system
    def identify(self) -> Identity:
        manufacturer, model, serial_no, firmware = self.query("*IDN?").split(",")
        return Identity(manufacturer, model, serial_no, firmware)

    def reset(self) -> None:
        self.write("*RST")

    def self_test(self) -> int:
        return int(self.query("*TST?"))

    def power_on(self) -> None:
        self.write("SYST:POW ON")

    def power_off(self) -> None:
        self.write("SYST:POW OFF")

    def state(self) -> str:
        return self.query("SYST:STAT?")

    def wait_until_ready(self, timeout_s: float) -> float:
        return self._poll("SYST:STAT?", "READY", timeout_s)

    def errors(self) -> list[tuple[int, str]]:
        """Drain the sensor's error queue."""
        drained = []
        while True:
            code, _, message = self.query("SYST:ERR?").partition(",")
            if int(code) == 0:
                return drained
            drained.append((int(code), message.strip('"')))

    # power
    def voltage(self) -> float:
        return float(self.query("MEAS:VOLT?"))

    def current(self) -> float:
        return float(self.query("MEAS:CURR?"))

    # thermal
    def temperature(self) -> float:
        return float(self.query("MEAS:TEMP?"))

    def cooler_status(self) -> str:
        return self.query("COOL:STAT?")

    def wait_cooler_ready(self, timeout_s: float) -> float:
        return self._poll("COOL:STAT?", "READY", timeout_s)

    # gimbal
    def point(self, azimuth: float, elevation: float) -> None:
        self.write(f"GIMB:AZ {azimuth}")
        self.write(f"GIMB:EL {elevation}")

    def home(self) -> None:
        self.write("GIMB:HOME")

    def position(self) -> tuple[float, float]:
        az, el = self.query("GIMB:POS?").split(",")
        return float(az), float(el)

    def wait_gimbal_idle(self, timeout_s: float) -> float:
        return self._poll("GIMB:STAT?", "IDLE", timeout_s)

    # imager
    def set_gain(self, gain: int) -> None:
        self.write(f"IMG:GAIN {gain}")

    def set_exposure(self, exposure_ms: float) -> None:
        self.write(f"IMG:EXP {exposure_ms}")

    def capture(self) -> Frame:
        fields = self.query("IMG:CAPT?").split(",")
        body = ",".join(fields[:4])
        return Frame(int(fields[0]), float(fields[1]), float(fields[2]), int(fields[3]), int(fields[4], 16), body)

    # simulator-only controls
    def inject_fault(self, name: str) -> None:
        self.write(f"SIM:FAULT {name}")

    def clear_faults(self) -> None:
        self.write("SIM:FAULT:CLR")

    def active_faults(self) -> list[str]:
        response = self.query("SIM:FAULT?")
        return [] if response == "NONE" else response.split(",")
