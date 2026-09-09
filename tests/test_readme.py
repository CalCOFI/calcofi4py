"""The README's examples run — every `python` block, as a reader would paste it.

A researcher copied the README's first release example on 2026-09-09 and it failed on a
column (`datetime_utc`) the release never had; nothing had ever executed the block. Now
the README is a test:

- release blocks run against the promoted release whenever the network is there
  (CI on every push);
- PostgreSQL blocks (any `cc_pg_*` call) need the tunnel and `~/.pgpass`, so they run
  only with `CALCOFI_PG_TEST=1`, like tests/test_pg_live.py;
- the release pipeline (CalCOFI/workflows `test_release.qmd`) runs this file against a
  freshly uploaded, not-yet-promoted release by setting `CALCOFI_RELEASE_VERSION` (and
  `CALCOFI_RELEASE_PREFIX` on a staging run) — so a schema change fails the release
  before it reaches a reader.

A block whose first line is `# readme: skip` is not executed (none is today); a bash block
never is. Each block runs in its own namespace, so every one must stand alone, exactly as
a reader pasting it would find.
"""
import os
import re
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.M | re.S)


def _online() -> bool:
    try:
        socket.create_connection(("storage.googleapis.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def readme_blocks() -> list[tuple[str, str]]:
    """[(label, code), …] for every ```python block, labelled by the nearest heading above it."""
    text = README.read_text()
    out = []
    for m in FENCE.finditer(text):
        heads = re.findall(r"^#+ +(.+)$", text[: m.start()], re.M)
        label = (heads[-1] if heads else "top").strip()
        out.append((f"{label} #{sum(1 for l, _ in out if l.startswith(label)) + 1}", m.group(1)))
    return out


BLOCKS = readme_blocks()


def test_readme_has_examples():
    assert len(BLOCKS) >= 3, "the README lost its python examples"
    assert any("cc_get_db(" in code for _, code in BLOCKS)


@pytest.mark.parametrize("label,code", BLOCKS, ids=[l for l, _ in BLOCKS])
def test_readme_block_runs(label, code):
    if code.lstrip().startswith("# readme: skip"):
        pytest.skip("block opts out with `# readme: skip`")
    needs_pg = "cc_pg_" in code
    if needs_pg and not os.environ.get("CALCOFI_PG_TEST"):
        pytest.skip("PostgreSQL block: set CALCOFI_PG_TEST=1 with a tunnel + ~/.pgpass")
    if not _online():
        pytest.skip("no network to storage.googleapis.com")
    ns: dict = {"__name__": "readme_block"}
    exec(compile(code, f"README.md [{label}]", "exec"), ns)  # noqa: S102 — the README is ours
