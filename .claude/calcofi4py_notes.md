# calcofi4py session notes

What was asked and what was done, one `## YYYY-MM-DD — summary title` section per day, newest first (the
`CHANGELOG.md` of the *work*, where `CHANGELOG.md` is the changelog of the *package*). Prompts
are quoted; mid-turn messages are listed under the prompt they interrupted. Commits and tags
are named so a reader can `git show` them. No secrets, ever.

## 2026-08-21 — changelog, 0.3.6 release, unattended release flow

Versions 0.3.5 → 0.3.6. Commits `ef94fbe`, `1fcfce9`, `3cdf937` (Ben), `bdb9384`; tag `v0.3.6`.
Server deployed (`server calcofi4py 0.3.6`). CI green on every push.

### 1. "where is the changelog (eg NEWS.md of R package) for this Python module? need to describe changes in each version change"

- *mid-turn:* "be sure to add datestamps on change history alongside version numbers"
- *mid-turn:* "and update CLAUDE.md accordingly to always push these aspects on change"

**Response.** There was none. Reconstructed `CHANGELOG.md` at the repo root from the 8
version-bump commits (`git log --date=short -G '^version' -- pyproject.toml`, then the `src/`
diff between each pair) — one `## X.Y.Z (YYYY-MM-DD)` section per version, 0.1.0 → 0.3.5, all
dated from git, user-facing changes only (signature changes, removed arguments, renamed
columns, fixes). Published on the docs site as the *Changelog* page by a new mkdocs hook
(`hooks/changelog.py`, `File.generated` from the root file — no copy in `docs/`; edit link
points at the real file). Enforced in `tests/test_docs.py`: newest heading must equal
`calcofi4py.__version__`, every heading dated, newest-first, no repeats, hook publishes the root
file. Added a *Changelog (CHANGELOG.md is not optional)* section to `CLAUDE.md` and folded it
into release step 1. Saved the dated-headings preference to memory. First draft had an
`## Unreleased` section for the docs-only commits after the `v0.3.5` tag.

### 2. "Unreleased does not make sense to me. Bump to 0.3.6 if need be, commit and push"

**Response.** Dropped the Unreleased concept everywhere — the changelog's top section became
`## 0.3.6 (2026-08-21)` ("Docs and tooling — no API change"), the test now rejects any heading
that is not a dated version, and `CLAUDE.md` says every user-facing change bumps the version
(patch for fixes/docs, minor for new functions) and gets a dated bullet in the same commit.
Bumped 0.3.6 in `pyproject.toml`, `__init__.py`, the `cc.__version__  # '0.3.6'` example lines
and the `@v0.3.6` pin example in README/docs. Re-ran `pip install -e .` because
`hooks/version.py` reads the *installed* metadata (site header still said 0.3.5 until then).
23 tests passed / 3 live-PG skipped, `mkdocs build --strict` clean. Commit `ef94fbe`, tag
`v0.3.6`, pushed both. Left the server deploy and the article re-render as "follow-ups" —
which prompted the next request.

### 3. "Deploy to server always, and add this instruction to CLAUDE.md"

- *mid-turn:* "Use my tunnel to bump version, and update CLAUDE.md / permissions for future"

**Response.** Ran `scripts/deploy_server.sh v0.3.6` → `server calcofi4py 0.3.6`. Rewrote
release step 4 as unconditional: every bump, docs-only included, never a follow-up, not done
until the script prints the version. Then tried to finish the bump through the tunnel: the
article render (`PYTHON=.venv/bin/python scripts/render_articles.sh`) opened `ssh -N calcofi`
fine but failed with `fe_sendauth: no password supplied` — no `~/.pgpass` on this Mac;
restored the committed notebook (`git checkout -- docs/articles`, since jupytext overwrites it
before nbconvert runs). Writing `.claude/settings.json` (the permission allowlist) was refused
by the auto-mode classifier twice (shell heredoc and the Write tool), so the JSON was handed to
Ben to add. `CLAUDE.md`: new step 2 *re-render the articles through the tunnel, every bump*
(with the pgpass troubleshooting line), and a *Run the whole checklist yourself, without
asking* paragraph naming the allowlist. Commit `1fcfce9`, pushed. Memory: release flow runs
unattended; pgpass missing.

### 4. "Ok, added .claude/settings.json and ~/.pgpass identical to CalCOFI server"

**Response.** Verified: 15 allow rules (committed by Ben as `3cdf937`); `~/.pgpass` mode 600
with `localhost` and `postgis` lines for role `bebest` (the `localhost` line is what the tunnel
needs). Render succeeded in 49 s — 15 code cells, no errors, the article prints
`calcofi4py 0.3.6`. Commit `bdb9384` ("articles: re-rendered for 0.3.6 through the tunnel"),
pushed; `test` and `docs` workflows green; no `ssh -N` left behind. Memory updated: pgpass and
allowlist in place; the classifier blocks Claude from writing `settings.json` itself.

### 5. "Summarize this session today with prompts and responses in @.claude/calcofi4py_notes.md and update CLAUDE.md to similarly track changes in future with most recent date change at top (similar to @CHANGELOG.md)"

- *mid-turn:* "add a summary title next to date header"

**Response.** This file, and a *Session notes* section in `CLAUDE.md` (append under today's
date at the top, `## YYYY-MM-DD — summary title`, prompts quoted, commits named, no secrets).
Committed with `CLAUDE.md` and pushed.

### Gotchas learned today

- `hooks/version.py` (and so the site header) reads the *installed* metadata — `pip install -e .`
  again after a bump or it keeps showing the old version.
- mkdocs `File.generated()` needs `config.plugins._current_plugin`, set only inside mkdocs'
  event dispatch — test hooks through `cfg.plugins.run_event("files", …)`, not by calling
  `on_files` directly.
- The README/docs example lines are `cc.__version__   …   # '0.3.6'` with wide spacing —
  match on `# '0.3.6'`, not `cc.__version__  # '0.3.6'`.
- `scripts/render_articles.sh`: jupytext overwrites the committed notebook *before* nbconvert
  executes it — on any failure `git checkout -- docs/articles`.
- The tunnel needs a `localhost:5432:…` line in `~/.pgpass`; the server's own line is `postgis`.
- The shell is zsh: `$pipestatus` (lowercase); `$PIPESTATUS` is empty.
- The auto-mode classifier will not let Claude write `.claude/settings.json` — give Ben the JSON.
- A docs-only bump still deploys to the server: the version the site quotes and the version
  `cc.__version__` prints on rstudio.calcofi.io must agree.
