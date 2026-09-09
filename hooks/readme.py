"""mkdocs hook: publish the repo-root README.md as the site's Home page.

One file, one truth (the same rule as hooks/changelog.py). README.md is what GitHub and
`pip` show and what tests/test_readme.py executes; it is injected here as `index.md` at
build time, so the Home page cannot drift from it and nothing is copied into docs/.
The one edit: the logo's absolute URL becomes the site-relative asset path.
"""
from pathlib import Path

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PAGE = "index.md"
LOGO_ABS = "https://calcofi.io/calcofi4py/assets/logo.svg"
LOGO_REL = "assets/logo.svg"


def readme_as_index() -> str:
    return README.read_text().replace(LOGO_ABS, LOGO_REL)


def on_files(files, config):
    files.append(File.generated(config, PAGE, content=readme_as_index()))
    return files


def on_page_context(context, page, config, nav):
    if page.file.src_uri == PAGE and config.repo_url:
        page.edit_url = f"{config.repo_url.rstrip('/')}/edit/main/README.md"
    return context
