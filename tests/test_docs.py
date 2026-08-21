"""Docs stay truthful about the version they show."""
import re
from pathlib import Path

import calcofi4py

ROOT = Path(__file__).resolve().parents[1]


def test_examples_quote_the_current_version():
    """README.md and docs/index.md open their examples with `cc.__version__  # '<ver>'`."""
    for f in ("README.md", "docs/index.md"):
        text = (ROOT / f).read_text()
        quoted = set(re.findall(r"cc\.__version__\s+# '([^']+)'", text))
        assert quoted == {calcofi4py.__version__}, f"{f} quotes {quoted}, package is {calcofi4py.__version__}"


def test_pyproject_matches_dunder_version():
    text = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^version = "([^"]+)"', text, re.M).group(1) == calcofi4py.__version__


def test_mkdocs_hook_reads_the_version():
    import importlib.util
    spec = importlib.util.spec_from_file_location("version_hook", ROOT / "hooks" / "version.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.calcofi4py_version() == calcofi4py.__version__


# ── changelog ────────────────────────────────────────────────────────────────

CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_HEADING = re.compile(r"^## (?P<ver>\d+\.\d+\.\d+) \((?P<date>\d{4}-\d{2}-\d{2})\)\s*$")


def _changelog_entries():
    """[(version, date), …] from the `## X.Y.Z (YYYY-MM-DD)` headings, top to bottom.

    Every `## ` heading is a dated version — no 'Unreleased' holding pen: a change on
    main bumps the version."""
    h2 = [l.rstrip() for l in CHANGELOG.read_text().splitlines() if l.startswith("## ")]
    assert h2, "CHANGELOG.md has no '## ' headings"
    undated = [l for l in h2 if not VERSION_HEADING.match(l)]
    assert not undated, f"every heading is '## X.Y.Z (YYYY-MM-DD)' — not: {undated}"
    return [(m["ver"], m["date"]) for m in map(VERSION_HEADING.match, h2)]


def test_changelog_newest_entry_is_the_current_version():
    """A version bump without its CHANGELOG.md entry (with a date) is a red test."""
    entries = _changelog_entries()
    assert entries[0][0] == calcofi4py.__version__, (
        f"CHANGELOG.md newest entry is {entries[0][0]}, package is {calcofi4py.__version__} — "
        "add '## <version> (<YYYY-MM-DD>)' at the top in the bump commit")


def test_changelog_is_newest_first_and_each_version_once():
    entries = _changelog_entries()
    versions = [tuple(int(x) for x in v.split(".")) for v, _ in entries]
    assert versions == sorted(versions, reverse=True), "versions must be newest first"
    assert len(set(versions)) == len(versions), "a version appears more than once"
    dates = [d for _, d in entries]
    assert dates == sorted(dates, reverse=True), "dates must be newest first"


def test_changelog_hook_publishes_the_root_file(tmp_path):
    """The site's Changelog page IS CHANGELOG.md (hooks/changelog.py), not a copy in docs/.

    Dispatched through mkdocs' own event loop, as in a real build (`File.generated`
    needs that context)."""
    pytest = __import__("pytest")
    pytest.importorskip("mkdocs")
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files

    cfg = MkDocsConfig(config_file_path=str(ROOT / "mkdocs.yml"))  # hooks resolve relative to it
    cfg.load_dict({"site_name": "t", "docs_dir": "docs", "site_dir": str(tmp_path / "site"),
                   "hooks": ["hooks/changelog.py"]})
    errors, _ = cfg.validate()
    assert not errors, errors
    files = cfg.plugins.run_event("files", Files([]), config=cfg)
    page = files.get_file_from_path("changelog.md")
    assert page is not None and page.content_string == CHANGELOG.read_text()
    assert not (ROOT / "docs" / "changelog.md").exists(), "keep the single source at the repo root"
