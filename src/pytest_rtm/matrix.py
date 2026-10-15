"""Build the traceability matrix from requirements, test links and outcomes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .requirements import Requirement

VERIFIED = "VERIFIED"
FAILED = "FAILED"
NOT_RUN = "NOT RUN"
NOT_COVERED = "NOT COVERED"
NO_EVIDENCE = "NO EVIDENCE"

STATUSES = (VERIFIED, FAILED, NOT_RUN, NOT_COVERED, NO_EVIDENCE)
GAPS = (NOT_RUN, NOT_COVERED, NO_EVIDENCE)


@dataclass
class Row:
    requirement: Requirement
    tests: list[tuple[str, str]] = field(default_factory=list)  # (test id, outcome)
    status: str = NOT_COVERED


@dataclass
class Matrix:
    rows: list[Row]
    untraced_tests: list[str]

    def counts(self) -> dict[str, int]:
        counted = Counter(row.status for row in self.rows)
        return {status: counted.get(status, 0) for status in STATUSES}

    @property
    def coverage(self) -> float:
        """Percentage of requirements that are VERIFIED."""
        return 100.0 * self.counts()[VERIFIED] / len(self.rows) if self.rows else 100.0

    @property
    def gaps(self) -> list[Row]:
        return [row for row in self.rows if row.status in GAPS]

    @property
    def failures(self) -> list[Row]:
        return [row for row in self.rows if row.status == FAILED]


def _status(req: Requirement, tests: list[tuple[str, str]], root: Path) -> str:
    if req.verification != "Test":
        return VERIFIED if (root / req.evidence).exists() else NO_EVIDENCE
    if not tests:
        return NOT_COVERED
    outcomes = {outcome for _, outcome in tests}
    if "failed" in outcomes:
        return FAILED
    if "passed" in outcomes:
        return VERIFIED
    return NOT_RUN


def build_matrix(
    requirements: list[Requirement],
    links: dict[str, list[str]],
    outcomes: dict[str, str],
    root: Path,
) -> Matrix:
    """``links`` maps test id -> requirement ids; ``outcomes`` maps test id -> outcome."""
    rows = {req.id: Row(req) for req in requirements}
    untraced = []
    for test_id, req_ids in links.items():
        if not req_ids:
            untraced.append(test_id)
        for req_id in req_ids:
            rows[req_id].tests.append((test_id, outcomes.get(test_id, "not run")))
    for row in rows.values():
        row.status = _status(row.requirement, row.tests, root)
    return Matrix(list(rows.values()), untraced)
