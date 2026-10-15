"""Measurement records and the SQLite results database.

The database is append-only across runs, so it builds up a history that can
be mined later for failure and trend analysis.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    station         TEXT,
    operator        TEXT,
    station_version TEXT,
    git_commit      TEXT,
    dut_model       TEXT,
    dut_serial      TEXT,
    dut_firmware    TEXT,
    injected_faults TEXT,
    comm_retries    INTEGER,
    outcome         TEXT
);
CREATE TABLE IF NOT EXISTS test_results (
    run_id       TEXT NOT NULL REFERENCES runs(run_id),
    test_id      TEXT NOT NULL,
    requirements TEXT,
    outcome      TEXT NOT NULL,
    duration_s   REAL,
    message      TEXT
);
CREATE TABLE IF NOT EXISTS measurements (
    run_id  TEXT NOT NULL REFERENCES runs(run_id),
    test_id TEXT NOT NULL,
    name    TEXT NOT NULL,
    value   REAL,
    low     REAL,
    high    REAL,
    units   TEXT,
    passed  INTEGER NOT NULL
);
"""


@dataclass
class Measurement:
    name: str
    value: float
    low: float | None = None
    high: float | None = None
    units: str = ""

    @property
    def passed(self) -> bool:
        if self.low is not None and self.value < self.low:
            return False
        if self.high is not None and self.value > self.high:
            return False
        return True

    def limits_text(self) -> str:
        if self.low is not None and self.high is not None:
            return f"{self.low:g} .. {self.high:g}"
        if self.low is not None:
            return f">= {self.low:g}"
        if self.high is not None:
            return f"<= {self.high:g}"
        return "(record only)"


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class

    test_id: str
    requirements: list[str]
    outcome: str
    duration_s: float
    message: str = ""
    measurements: list[Measurement] = field(default_factory=list)


@dataclass
class RunRecord:
    run_id: str
    started_at: str
    station: str
    operator: str
    station_version: str
    git_commit: str
    dut_model: str = ""
    dut_serial: str = ""
    dut_firmware: str = ""
    injected_faults: str = ""
    finished_at: str = ""
    comm_retries: int = 0
    outcome: str = ""
    results: list[TestResult] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        for result in self.results:
            counts[result.outcome] = counts.get(result.outcome, 0) + 1
        return counts


class ResultsDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def save(self, run: RunRecord) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.started_at, run.finished_at, run.station, run.operator,
                 run.station_version, run.git_commit, run.dut_model, run.dut_serial,
                 run.dut_firmware, run.injected_faults, run.comm_retries, run.outcome),
            )
            for result in run.results:
                self._conn.execute(
                    "INSERT INTO test_results VALUES (?,?,?,?,?,?)",
                    (run.run_id, result.test_id, ",".join(result.requirements),
                     result.outcome, result.duration_s, result.message),
                )
                self._conn.executemany(
                    "INSERT INTO measurements VALUES (?,?,?,?,?,?,?,?)",
                    [(run.run_id, result.test_id, m.name, m.value, m.low, m.high, m.units, int(m.passed))
                     for m in result.measurements],
                )

    def measurements(self, run_id: str) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        return self._conn.execute(
            "SELECT * FROM measurements WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()

    def run(self, run_id: str) -> sqlite3.Row | None:
        self._conn.row_factory = sqlite3.Row
        return self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
