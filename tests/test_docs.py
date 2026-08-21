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
