"""Verification of the station's communication layer: checksums and retries."""

import socket
import threading

import pytest

from test_station.driver import CommError, EOSensor, checksum, unframe


def framed(payload: str) -> bytes:
    return f"{payload}*{checksum(payload)}\n".encode("ascii")


@pytest.mark.req("TS-001")
def test_valid_frame_accepted():
    assert unframe(framed("28.01")) == "28.01"


@pytest.mark.req("TS-001")
@pytest.mark.parametrize("raw", [
    b"28.01*00\n",          # wrong checksum
    b"28.01\n",             # checksum missing
    b"28.0",                # truncated (timeout mid-line)
    b"",                    # no response
    b"\xff\xfe*00\n",       # line noise
], ids=["bad-checksum", "no-checksum", "truncated", "empty", "noise"])
def test_invalid_frames_rejected(raw):
    with pytest.raises(CommError):
        unframe(raw)


@pytest.mark.req("TS-001", "TS-002")
def test_corrupted_responses_discarded_and_retried(sensor, inject):
    expected = sensor.identify()
    inject("COMM_CORRUPT")
    before = sensor.retries_used
    readings = [sensor.identify() for _ in range(9)]
    assert all(r == expected for r in readings), "a corrupted response leaked through"
    assert sensor.retries_used > before


@pytest.mark.req("TS-002")
def test_dropped_responses_retried(sensor, inject):
    inject("COMM_DROP")
    before = sensor.retries_used
    states = [sensor.state() for _ in range(9)]
    assert states == ["READY"] * 9
    assert sensor.retries_used > before


@pytest.fixture
def silent_device():
    """A TCP endpoint that accepts connections but never answers."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    stop = threading.Event()

    def swallow():
        conn, _ = listener.accept()
        conn.settimeout(0.05)
        while not stop.is_set():
            try:
                if not conn.recv(1024):
                    break
            except socket.timeout:
                pass
        conn.close()

    threading.Thread(target=swallow, daemon=True).start()
    yield f"socket://127.0.0.1:{listener.getsockname()[1]}"
    stop.set()
    listener.close()


@pytest.mark.req("TS-002")
def test_comm_failure_declared_after_two_retries(silent_device):
    with EOSensor(silent_device, timeout=0.05, retries=2) as dut:
        with pytest.raises(CommError, match="after 3 attempts"):
            dut.identify()
        assert [attempt for *_, attempt in dut.comm_log] == [0, 1, 2]
        assert dut.retries_used == 2
