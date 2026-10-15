"""pytest integration that turns pytest into a test executive.

Provides:
  * command-line options to select the DUT and inject faults,
  * the ``station``, ``sensor``, ``measure`` and ``inject`` fixtures,
  * per-run records written to SQLite, an HTML report and a raw comm log.

Loaded through ``-p test_station.plugin`` in pyproject.toml.
"""

from __future__ import annotations

import getpass
import platform
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from . import __version__
from .driver import DeviceError, EOSensor
from .report import render_report, write_comm_log
from .results import Measurement, ResultsDB, RunRecord, TestResult

DEFAULT_SIM_SPEED = 10.0

STATION = pytest.StashKey["Station"]()
MEASUREMENTS = pytest.StashKey[list]()
RETRIES_AT_START = pytest.StashKey[int]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("station", "EOS-100 test station")
    group.addoption("--dut-url", default=None,
                    help="connect to an existing DUT (COM3, socket://host:5025); default launches the simulator")
    group.addoption("--time-scale", type=float, default=None,
                    help=f"DUT clock speed-up factor (default {DEFAULT_SIM_SPEED:g} for the built-in simulator, 1 otherwise)")
    group.addoption("--inject-fault", action="append", default=[], metavar="FAULT",
                    help="inject a simulator fault for the whole run (repeatable)")
    group.addoption("--report-dir", default="reports", help="where to write the report, database and comm log")
    group.addoption("--operator", default=None, help="operator name recorded with the run")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _git_commit(root: Path) -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _operator() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


class Station:
    """Session-wide state: the DUT connection and the record of this run."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        opt = config.option
        self.run_faults: list[str] = [f.upper() for f in opt.inject_fault]
        self.report_dir = Path(opt.report_dir)
        self.simulated = opt.dut_url is None
        self.server = None
        self.sensor: EOSensor | None = None
        self.outputs: list[Path] = []
        self.run = RunRecord(
            run_id=datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            started_at=_now(),
            station=platform.node(),
            operator=opt.operator or _operator(),
            station_version=__version__,
            git_commit=_git_commit(config.rootpath),
            injected_faults=",".join(self.run_faults),
        )

    def connect(self) -> EOSensor:
        if self.sensor is not None:
            return self.sensor
        opt = self.config.option
        if self.simulated:
            from eos_sim import Device, SimulatorServer

            scale = opt.time_scale or DEFAULT_SIM_SPEED
            self.server = SimulatorServer(Device(speed=scale), port=0).start()
            url = self.server.url
        else:
            scale = opt.time_scale or 1.0
            url = opt.dut_url
        self.sensor = EOSensor(url, time_scale=scale).open()
        identity = self.sensor.identify()
        self.run.dut_model = identity.model
        self.run.dut_serial = identity.serial
        self.run.dut_firmware = identity.firmware
        self.sensor.clear_faults()
        self.apply_run_faults()
        return self.sensor

    def apply_run_faults(self) -> None:
        for fault in self.run_faults:
            self.sensor.inject_fault(fault)

    def finish(self) -> None:
        run = self.run
        run.finished_at = _now()
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run.outcome = "FAIL" if any(r.outcome == "failed" for r in run.results) else "PASS"
        if self.sensor is not None:
            run.comm_retries = self.sensor.retries_used
            try:
                self.sensor.power_off()  # leave the DUT in a safe state
            except Exception:
                pass
            self.outputs.append(write_comm_log(self.sensor.comm_log, self.report_dir / "comm_log.tsv"))
            self.sensor.close()
        if self.server is not None:
            self.server.stop()
        db = ResultsDB(self.report_dir / "results.db")
        try:
            db.save(run)
        finally:
            db.close()
        self.outputs.append(self.report_dir / "results.db")
        self.outputs.insert(0, render_report(run, self.report_dir / "test_report.html"))


def pytest_configure(config: pytest.Config) -> None:
    config.stash[STATION] = Station(config)


# ------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def station(pytestconfig: pytest.Config) -> Station:
    station = pytestconfig.stash[STATION]
    station.connect()
    return station


@pytest.fixture
def sensor(station: Station) -> EOSensor:
    """The DUT, powered, READY and reset to default settings."""
    dut = station.sensor
    if dut.state() == "OFF":
        dut.power_on()
    dut.wait_until_ready(timeout_s=10.0)
    dut.reset()
    return dut


@pytest.fixture
def measure(request: pytest.FixtureRequest):
    """Record a measurement against its limits, then fail the test if it is out of limits.

        measure("bus voltage", v, low=27.0, high=29.0, units="V")
    """
    records = request.node.stash.setdefault(MEASUREMENTS, [])

    def _measure(name: str, value: float, low: float | None = None,
                 high: float | None = None, units: str = "") -> float:
        record = Measurement(name, float(value), low, high, units)
        records.append(record)
        if not record.passed:
            raise AssertionError(f"{name} = {value:g} {units} is outside limits {record.limits_text()}")
        return value

    return _measure


@pytest.fixture
def inject(station: Station, sensor: EOSensor):
    """Inject simulator faults for one test; they are removed afterwards."""
    try:
        sensor.active_faults()
    except DeviceError:
        pytest.skip("DUT does not support fault injection (real hardware)")
    injected: list[str] = []

    def _inject(fault: str) -> None:
        sensor.inject_fault(fault)
        injected.append(fault)

    yield _inject
    if injected:
        sensor.clear_faults()
        station.apply_run_faults()


# ---------------------------------------------------------------------- hooks


def _message(report: pytest.TestReport) -> str:
    if report.passed:
        return ""
    if report.skipped and isinstance(report.longrepr, tuple):
        return report.longrepr[2]
    crash = getattr(report.longrepr, "reprcrash", None)
    return crash.message if crash is not None else str(report.longrepr)


def _retries(station: Station) -> int:
    return station.sensor.retries_used if station.sensor is not None else 0


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> None:
    item.stash[RETRIES_AT_START] = _retries(item.config.stash[STATION])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    station = item.config.stash[STATION]
    run = station.run
    if report.when == "call" or (report.when == "setup" and not report.passed):
        requirements = [req for mark in item.iter_markers("req") for req in mark.args]
        retries = _retries(station) - item.stash.get(RETRIES_AT_START, _retries(station))
        message = _message(report)
        if report.failed and retries and item.get_closest_marker("timing"):
            # Retry latency is indistinguishable from device delay, so point
            # the engineer at the link before they suspect the hardware.
            message += (f"\n[station] {retries} comm retries during this timing test; "
                        "elapsed-time results may include retry latency")
        run.results.append(TestResult(
            test_id=item.nodeid,
            requirements=requirements,
            outcome=report.outcome,
            duration_s=report.duration,
            message=message,
            measurements=list(item.stash.get(MEASUREMENTS, [])),
            comm_retries=retries,
        ))
    elif report.when == "teardown" and report.failed and run.results:
        last = run.results[-1]
        if last.test_id == item.nodeid:
            last.outcome = "failed"
            last.message = last.message or f"teardown: {_message(report)}"


def pytest_sessionfinish(session: pytest.Session) -> None:
    station = session.config.stash.get(STATION, None)
    if station is not None and station.sensor is not None:
        station.finish()


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    station = config.stash.get(STATION, None)
    if station is None or not station.outputs:
        return
    terminalreporter.section("test station")
    terminalreporter.write_line(f"Run {station.run.run_id}: {station.run.outcome} "
                                f"(DUT {station.run.dut_model} {station.run.dut_serial}, "
                                f"{station.run.comm_retries} comm retries)")
    for path in station.outputs:
        terminalreporter.write_line(f"  {path}")
