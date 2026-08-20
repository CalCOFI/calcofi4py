"""Reproducibility: what software and data-rule versions produced a result."""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["cc_session_info"]

_DEFAULT_PKGS = ("calcofi4py", "duckdb", "psycopg", "pandas", "plotly",
                 "numpy", "jupyter_core", "ipykernel")


def _repo_commit(path: str | Path, subpath: str | None = None) -> str:
    """``<short-hash> <iso-date> (<dirty?>)`` of the last commit touching ``subpath``."""
    try:
        args = ["git", "-C", str(path), "log", "-1", "--format=%h %cs"]
        if subpath:
            args += ["--", subpath]
        out = subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--", subpath or "."],
            capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{out}{' +uncommitted-changes' if dirty else ''}" if out else "not a git repo"
    except Exception as e:  # pragma: no cover
        return f"unavailable ({e.__class__.__name__})"


def cc_session_info(
    packages: tuple[str, ...] = _DEFAULT_PKGS,
    repos: dict[str, tuple[str, str | None]] | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """The Python equivalent of R's ``devtools::session_info()``, as printable text.

    Made for the tail of a QA/QC notebook: when the rendered HTML is kept as the
    **archive of a cleaning run**, this block records exactly what produced it —
    Python, platform, package versions (``calcofi4py`` above all), and the git
    commit of any data-rule directory the run depended on.

    :param packages: distributions to report (missing ones are noted, not fatal)
    :param repos: ``{label: (repo_path, subpath_or_None)}`` — each reports the
        last commit touching ``subpath`` (e.g. the QC rule registry), plus a
        dirty-tree warning so an uncommitted rule change cannot masquerade as a
        committed one
    :param extra: extra ``{label: value}`` lines (e.g. the PostgreSQL server
        version captured while the connection was open)

    >>> print(cc_session_info(repos={"qc_rules": (".", "metadata/qc_rules")}))
    """
    lines = [
        f"rendered_utc    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"python          {sys.version.split()[0]} ({platform.python_implementation()})",
        f"platform        {platform.platform()}",
        f"executable      {sys.executable}",
        "",
        "packages",
    ]
    for p in packages:
        try:
            lines.append(f"  {p:<14}{importlib.metadata.version(p)}")
        except importlib.metadata.PackageNotFoundError:
            lines.append(f"  {p:<14}(not installed)")
    if repos:
        lines += ["", "data-rule / repo versions (last commit touching the path)"]
        for label, (path, sub) in repos.items():
            lines.append(f"  {label:<14}{_repo_commit(path, sub)}")
    if extra:
        lines += ["", "environment"]
        for k, v in extra.items():
            lines.append(f"  {k:<14}{v}")
    return "\n".join(lines)
