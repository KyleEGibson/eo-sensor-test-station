"""pytest hooks for requirements traceability.

Configuration (pyproject.toml ``[tool.pytest.ini_options]`` or CLI):
    rtm_requirements / --rtm-requirements   path to the YAML requirements file
    rtm_output       / --rtm-output         directory for rtm.html/.xlsx/.json/.md
    --rtm-strict     fail the run if any requirement lacks passing verification
    --no-rtm         disable the plugin for this run
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .matrix import Matrix, build_matrix
from .requirements import RequirementsError, load_requirements
from .writers import write_all

_SEVERITY = {"passed": 0, "skipped": 1, "failed": 2}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini("rtm_requirements", "YAML requirements file for the traceability matrix")
    parser.addini("rtm_output", "output directory for the traceability matrix", default="reports")
    group = parser.getgroup("rtm", "requirements traceability")
    group.addoption("--rtm-requirements", default=None, help="YAML requirements file (overrides ini)")
    group.addoption("--rtm-output", default=None, help="output directory (overrides ini)")
    group.addoption("--rtm-strict", action="store_true",
                    help="fail the run if any requirement is not covered, not run or lacks evidence")
    group.addoption("--no-rtm", action="store_true", help="disable traceability for this run")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(*ids): link a test to the requirement IDs it verifies")
    if config.option.no_rtm:
        return
    if config.option.rtm_requirements:
        source = Path(config.option.rtm_requirements)
    elif config.getini("rtm_requirements"):
        source = config.rootpath / config.getini("rtm_requirements")
    else:
        return
    out_dir = Path(config.option.rtm_output) if config.option.rtm_output else config.rootpath / config.getini("rtm_output")
    try:
        requirements = load_requirements(source)
    except RequirementsError as exc:
        raise pytest.UsageError(f"pytest-rtm: {exc}") from None
    config.pluginmanager.register(TraceabilityCollector(config, source, requirements, out_dir), "rtm-collector")


class TraceabilityCollector:
    def __init__(self, config, source, requirements, out_dir) -> None:
        self.config = config
        self.source = source
        self.requirements = requirements
        self.out_dir = out_dir
        self.links: dict[str, list[str]] = {}
        self.outcomes: dict[str, str] = {}
        self.matrix: Matrix | None = None
        self.outputs: list[Path] = []

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        known = {req.id for req in self.requirements}
        problems = []
        links = {}
        for item in session.items:
            ids = []
            for mark in item.iter_markers("req"):
                if not mark.args:
                    problems.append(f"{item.nodeid}: @pytest.mark.req needs at least one requirement ID")
                ids.extend(str(arg) for arg in mark.args)
            unknown = sorted(set(ids) - known)
            if unknown:
                problems.append(f"{item.nodeid}: unknown requirement ID(s) {', '.join(unknown)}")
            links[item.nodeid] = list(dict.fromkeys(ids))
        if problems:
            raise pytest.UsageError("pytest-rtm: broken trace links\n  " + "\n  ".join(problems))
        self.links = links

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" or not report.passed:
            previous = self.outcomes.get(report.nodeid, "passed")
            if _SEVERITY[report.outcome] >= _SEVERITY[previous]:
                self.outcomes[report.nodeid] = report.outcome

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        if not self.links:
            return
        self.matrix = build_matrix(self.requirements, self.links, self.outcomes, self.config.rootpath)
        title = f"{self.source.stem} traceability"
        try:
            import yaml

            doc = yaml.safe_load(self.source.read_text(encoding="utf-8"))
            if doc.get("document"):
                title = f"{doc['document']} Rev {doc.get('revision', '-')}"
        except Exception:
            pass
        self.outputs = write_all(self.matrix, self.out_dir, title)
        if self.config.option.rtm_strict and self.matrix.gaps and session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.matrix is None:
            return
        tr = terminalreporter
        tr.section("requirements traceability")
        counts = ", ".join(f"{n} {status.lower()}" for status, n in self.matrix.counts().items() if n)
        tr.write_line(f"{len(self.matrix.rows)} requirements: {counts} ({self.matrix.coverage:.1f}% verified)")
        for row in self.matrix.failures:
            tr.write_line(f"  FAILED       {row.requirement.id}: {row.requirement.text}", red=True)
        for row in self.matrix.gaps:
            tr.write_line(f"  {row.status:<12} {row.requirement.id}: {row.requirement.text}", yellow=True)
        if self.config.option.rtm_strict and self.matrix.gaps:
            tr.write_line("--rtm-strict: run marked as failed because of traceability gaps", red=True)
        for path in self.outputs:
            tr.write_line(f"  {path}")
