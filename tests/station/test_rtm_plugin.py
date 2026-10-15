"""Verification of the requirements traceability plugin (pytest_rtm).

Each test builds a throwaway project with pytester and runs pytest on it.
"""

import json

import openpyxl
import pytest

from pytest_rtm import RequirementsError, load_requirements

REQUIREMENTS = """
document: SRS-DEMO
revision: A
requirements:
  - {id: R-1, text: Passing requirement}
  - {id: R-2, text: Failing requirement}
  - {id: R-3, text: Requirement nobody tests}
  - {id: R-4, text: Inspected requirement, verification: Inspection, evidence: docs/icd.md}
  - {id: R-5, text: Analysis with missing evidence, verification: Analysis, evidence: docs/missing.md}
"""

TESTS = """
import pytest

@pytest.mark.req("R-1")
def test_one():
    pass

@pytest.mark.req("R-2")
def test_two():
    assert False

@pytest.mark.req("R-1", "R-2")
def test_shared():
    pass

def test_untraced():
    pass
"""


@pytest.fixture
def project(pytester):
    pytester.makefile(".yaml", requirements=REQUIREMENTS)
    pytester.mkdir("docs")
    (pytester.path / "docs" / "icd.md").write_text("# ICD\n")
    pytester.makeini("[pytest]\nrtm_requirements = requirements.yaml\nrtm_output = out\n")
    return pytester


def rtm(pytester):
    data = json.loads((pytester.path / "out" / "rtm.json").read_text())
    return {r["id"]: r for r in data["requirements"]}, data


@pytest.mark.req("TS-006")
def test_status_of_each_requirement(project):
    project.makepyfile(test_demo=TESTS)
    result = project.runpytest()
    result.assert_outcomes(passed=3, failed=1)
    rows, data = rtm(project)
    assert rows["R-1"]["status"] == "VERIFIED"
    assert rows["R-2"]["status"] == "FAILED"          # one linked test failed
    assert rows["R-3"]["status"] == "NOT COVERED"
    assert rows["R-4"]["status"] == "VERIFIED"        # evidence file exists
    assert rows["R-5"]["status"] == "NO EVIDENCE"
    assert [t["id"] for t in rows["R-1"]["tests"]] == ["test_demo.py::test_one", "test_demo.py::test_shared"]
    assert data["untraced_tests"] == ["test_demo.py::test_untraced"]
    assert data["coverage_percent"] == 40.0
    result.stdout.fnmatch_lines(["*requirements traceability*", "*5 requirements: 2 verified, 1 failed*"])


@pytest.mark.req("TS-006")
def test_strict_mode_fails_run_on_gaps(project):
    project.makepyfile(test_demo="""
        import pytest
        @pytest.mark.req("R-1")
        def test_one():
            pass
    """)
    assert project.runpytest().ret == pytest.ExitCode.OK
    strict = project.runpytest("--rtm-strict")
    assert strict.ret == pytest.ExitCode.TESTS_FAILED
    strict.stdout.fnmatch_lines(["*NOT COVERED*R-2*", "*--rtm-strict: run marked as failed*"])


@pytest.mark.req("TS-006")
def test_skipped_tests_do_not_verify(project):
    project.makepyfile(test_demo="""
        import pytest
        @pytest.mark.req("R-1")
        @pytest.mark.skip(reason="fixture unavailable")
        def test_one():
            pass
    """)
    project.runpytest()
    rows, _ = rtm(project)
    assert rows["R-1"]["status"] == "NOT RUN"


@pytest.mark.req("TS-007")
def test_unknown_requirement_id_is_rejected(project):
    project.makepyfile(test_demo="""
        import pytest
        @pytest.mark.req("R-99")
        def test_typo():
            pass
    """)
    result = project.runpytest()
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*unknown requirement ID(s) R-99*"])


@pytest.mark.req("TS-006")
def test_all_report_formats_written(project):
    project.makepyfile(test_demo=TESTS)
    project.runpytest()
    out = project.path / "out"
    assert {p.name for p in out.iterdir()} >= {"rtm.html", "rtm.xlsx", "rtm.json", "rtm.md"}
    html = (out / "rtm.html").read_text(encoding="utf-8")
    assert "SRS-DEMO Rev A" in html and "R-5" in html
    workbook = openpyxl.load_workbook(out / "rtm.xlsx")
    assert workbook.sheetnames == ["RTM", "Tests", "Summary"]
    assert workbook["RTM"]["A2"].value == "R-1"
    assert "| R-3 | Test | 0 | NOT COVERED |" in (out / "rtm.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("bad, message", [
    ("requirements:\n  - {id: A, text: x}\n  - {id: A, text: y}\n", "duplicate id A"),
    ("requirements:\n  - {id: A, text: x, verification: Guess}\n", "verification must be one of"),
    ("requirements:\n  - {id: A, text: x, verification: Inspection}\n", "requires an 'evidence' path"),
    ("requirements:\n  - {text: no id}\n", "'id' and 'text' are required"),
])
def test_requirements_file_validation(tmp_path, bad, message):
    path = tmp_path / "reqs.yaml"
    path.write_text(bad)
    with pytest.raises(RequirementsError, match=message):
        load_requirements(path)
