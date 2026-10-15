"""pytest-rtm: requirements traceability matrix generation for pytest.

Link tests to requirements with ``@pytest.mark.req("SYS-001")`` and point the
plugin at a YAML requirements file. Every run produces an RTM in HTML, Excel,
JSON and Markdown, and ``--rtm-strict`` fails the run on coverage gaps.
"""

from .matrix import Matrix, Row, build_matrix
from .requirements import Requirement, RequirementsError, load_requirements

__all__ = ["Matrix", "Row", "build_matrix", "Requirement", "RequirementsError", "load_requirements"]
