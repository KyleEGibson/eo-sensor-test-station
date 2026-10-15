"""Render the per-run HTML test report."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .results import RunRecord

_env = Environment(
    loader=PackageLoader("test_station", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def render_report(run: RunRecord, path: str | Path, rtm_href: str | None = "rtm.html") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = _env.get_template("report.html.j2").render(run=run, counts=run.counts(), rtm_href=rtm_href)
    path.write_text(html, encoding="utf-8")
    return path


def write_comm_log(log: list[tuple[float, str, str, int]], path: str | Path) -> Path:
    """Write the raw command/response transcript used for troubleshooting."""
    from datetime import datetime

    path = Path(path)
    lines = ["timestamp\tattempt\ttx\trx"]
    for stamp, tx, rx, attempt in log:
        when = datetime.fromtimestamp(stamp).isoformat(timespec="milliseconds")
        lines.append(f"{when}\t{attempt}\t{tx}\t{rx or '<no response>'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
