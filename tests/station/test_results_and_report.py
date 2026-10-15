"""Verification of result recording and report generation."""

import pytest

from test_station.plugin import MEASUREMENTS
from test_station.report import render_report
from test_station.results import Measurement, ResultsDB, RunRecord, TestResult


def sample_run(outcome="PASS") -> RunRecord:
    run = RunRecord(
        run_id="20260101-120000-abcd", started_at="2026-01-01T12:00:00", station="BENCH-01",
        operator="kgibson", station_version="1.0.0", git_commit="1a2b3c4",
        dut_model="EOS-100", dut_serial="SN000777", dut_firmware="2.4.1",
        finished_at="2026-01-01T12:00:09", outcome=outcome,
    )
    run.results.append(TestResult(
        "tests/component/test_power.py::test_bus_voltage", ["SYS-005"], "passed", 0.12,
        measurements=[Measurement("bus voltage", 28.02, 27.0, 29.0, "V")],
    ))
    run.results.append(TestResult(
        "tests/component/test_imager.py::test_dead_pixel_count", ["SYS-031"], "failed", 0.05,
        message="worst-case dead pixels = 147 px is outside limits <= 5",
        measurements=[Measurement("dead pixels", 147, None, 5, "px")],
    ))
    return run


@pytest.mark.req("TS-003")
def test_measurements_round_trip_through_database(tmp_path):
    db = ResultsDB(tmp_path / "results.db")
    try:
        db.save(sample_run())
        rows = db.measurements("20260101-120000-abcd")
        assert [(r["name"], r["value"], r["low"], r["high"], r["units"], r["passed"]) for r in rows] == [
            ("bus voltage", 28.02, 27.0, 29.0, "V", 1),
            ("dead pixels", 147.0, None, 5.0, "px", 0),
        ]
        assert db.run("20260101-120000-abcd")["dut_serial"] == "SN000777"
    finally:
        db.close()


@pytest.mark.req("TS-003")
def test_measure_fixture_records_before_judging(measure, request):
    measure("in limits", 1.5, low=1, high=2, units="V")
    with pytest.raises(AssertionError, match="outside limits 1 .. 2"):
        measure("out of limits", 2.5, low=1, high=2, units="V")
    recorded = request.node.stash[MEASUREMENTS]
    assert [(m.name, m.passed) for m in recorded] == [("in limits", True), ("out of limits", False)]
    recorded.clear()  # keep this self-test's deliberate failure out of the run report


@pytest.mark.req("TS-003", "TS-004")
def test_run_outputs_created_in_new_report_dir(pytester):
    """Regression: the comm log was written before the report directory existed."""
    pytester.makepyfile(test_dut="""
        def test_identify(sensor, measure):
            measure("bus voltage", sensor.voltage(), low=27, high=29, units="V")
    """)
    result = pytester.runpytest("-p", "test_station.plugin", "--no-rtm", "--report-dir", "fresh/nested")
    result.assert_outcomes(passed=1)
    out = pytester.path / "fresh" / "nested"
    assert {p.name for p in out.iterdir()} == {"test_report.html", "comm_log.tsv", "results.db"}


@pytest.mark.req("TS-004")
def test_report_identifies_dut_and_station(tmp_path):
    html = render_report(sample_run(outcome="FAIL"), tmp_path / "report.html").read_text(encoding="utf-8")
    for expected in ["EOS-100", "SN000777", "2.4.1", "v1.0.0", "1a2b3c4", "BENCH-01", "FAIL",
                     "1 passed", "1 failed", "outside limits &lt;= 5", "rtm.html"]:
        assert expected in html, expected
