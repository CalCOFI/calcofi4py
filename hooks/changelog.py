"""mkdocs hook: publish the repo-root CHANGELOG.md as the site's Changelog page.

One file, one truth. CHANGELOG.md lives at the repo root — next to pyproject.toml, where
GitHub and `git log` show it — and is injected here as `changelog.md` at build time, so
the page cannot drift from the file and nothing is copied into docs/. The page's
"edit" link points at the real file.
"""
from pathlib import Path

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PAGE = "changelog.md"


def on_files(files, config):
    files.append(File.generated(config, PAGE, content=CHANGELOG.read_text()))
    return files


def on_page_context(context, page, config, nav):
    # generated files get no edit link by default; send it to the real file
    if page.file.src_uri == PAGE and config.repo_url:
        page.edit_url = f"{config.repo_url.rstrip('/')}/edit/main/CHANGELOG.md"
    return context
