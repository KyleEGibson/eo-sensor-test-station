"""Load and validate a YAML requirements specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

METHODS = ("Test", "Inspection", "Analysis", "Demonstration")


class RequirementsError(ValueError):
    pass


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    verification: str = "Test"
    category: str = ""
    evidence: str = ""


def load_requirements(path: str | Path) -> list[Requirement]:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise RequirementsError(f"requirements file not found: {path}") from None
    entries = data.get("requirements") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise RequirementsError(f"{path}: expected a top-level 'requirements' list")

    requirements: list[Requirement] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{path}: requirement #{index + 1}"
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("text"):
            raise RequirementsError(f"{where}: 'id' and 'text' are required")
        req = Requirement(
            id=str(entry["id"]),
            text=str(entry["text"]).strip(),
            verification=str(entry.get("verification", "Test")),
            category=str(entry.get("category", "")),
            evidence=str(entry.get("evidence", "")),
        )
        if req.id in seen:
            raise RequirementsError(f"{where}: duplicate id {req.id}")
        if req.verification not in METHODS:
            raise RequirementsError(f"{where} ({req.id}): verification must be one of {', '.join(METHODS)}")
        if req.verification != "Test" and not req.evidence:
            raise RequirementsError(f"{where} ({req.id}): {req.verification} requires an 'evidence' path")
        seen.add(req.id)
        requirements.append(req)
    return requirements
