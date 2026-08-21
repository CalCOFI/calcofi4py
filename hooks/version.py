"""mkdocs hook: stamp the documented calcofi4py version onto the site.

The site is built from the package at the same commit (`pip install -e ".[docs]"` in
.github/workflows/docs.yml), so the installed version IS the documented version. It goes
into the header / page titles ("calcofi4py v0.3.5") and replaces ``{{ calcofi4py_version }}``
in any Markdown page. No hand-maintained number anywhere on the site.
"""
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PLACEHOLDER = "{{ calcofi4py_version }}"


def calcofi4py_version() -> str:
    try:
        return version("calcofi4py")
    except PackageNotFoundError:  # building docs without the package installed
        init = Path(__file__).resolve().parents[1] / "src" / "calcofi4py" / "__init__.py"
        return re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text()).group(1)


def on_config(config):
    v = calcofi4py_version()
    config.extra["calcofi4py_version"] = v
    config.site_name = f"calcofi4py v{v}"
    return config


def on_page_markdown(markdown, page, config, files):
    return markdown.replace(PLACEHOLDER, config.extra["calcofi4py_version"])
