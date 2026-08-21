# CLAUDE.md — calcofi4py

Thin Python sibling of `calcofi4r` (`../calcofi4r`): the public database releases (DuckDB
over Parquet on GCS, no credentials) and the CTD team's PostgreSQL working database
(private, over SSH). **Keep the two packages in step** — same verbs, same defaults, same
conventions (`cc_*` names, `~/.pgpass` for secrets, `PGHOST`/`PGPORT`/`PGUSER` overrides).
Docs are a "Python pkgdown": mkdocs-material + mkdocstrings → gh-pages →
https://calcofi.io/calcofi4py/.

## Commands

```bash
pip install -e ".[dev]"
pytest -q                                        # pure-logic + (online) release tests
CALCOFI_PG_TEST=1 PGPORT=15432 pytest -q         # + live PostgreSQL tests (they open the tunnel themselves)
mkdocs serve                                     # docs locally (pip install -e ".[docs]")
PYTHON=.venv/bin/python scripts/render_articles.sh    # re-render docs/articles/*.ipynb (needs an account)
scripts/deploy_server.sh                         # upgrade the SERVER copy (see below)
```

Use `PGPORT=15432` locally when something else holds 5432 (a stale tunnel, a local
Postgres): `cc_pg_tunnel()` leaves an occupied port alone and you silently talk to the
wrong server.

## Releasing — the server copy is part of the release

1. Bump the version in `pyproject.toml`, `src/calcofi4py/__init__.py`, **the
   `cc.__version__  # '<ver>'` lines that open the README / docs examples, and
   `CHANGELOG.md`** — a new `## X.Y.Z (YYYY-MM-DD)` section at the top, today's date, one
   bullet per user-facing change (see *Changelog* below). `tests/test_docs.py` fails if any
   of the four disagree. The site header shows the installed version automatically
   (`hooks/version.py` reads the *installed* metadata — `pip install -e .` again after a
   bump or it keeps showing the old one); nothing else is hand-maintained.
2. Push to `main` → `.github/workflows/docs.yml` redeploys the docs; `test.yml` runs. Then
   **tag it**: `git tag -a vX.Y.Z -m "calcofi4py X.Y.Z — …" && git push origin vX.Y.Z` — users pin
   with `@vX.Y.Z`, and `scripts/deploy_server.sh vX.Y.Z` takes a tag. (Tags start at v0.3.5;
   earlier versions are reachable only by commit SHA.)
3. **Always upgrade the server: `scripts/deploy_server.sh`.** The CTD team runs the examples
   in RStudio's Python console on rstudio.calcofi.io, whose reticulate interpreter is the
   rstudio container's `/opt/venv`. That copy is baked into the image only at build time
   (`CalCOFI/server` `rstudio/Dockerfile`), so after a bump it is stale until this script
   runs. It bit us on 2026-08-21: the README example called `cc_withdraw_flags()`, the
   server had the previous version, the flag was proposed and the undo threw.
4. Tell whoever is mid-session to *Session → Restart R*: reticulate embeds Python once per
   R session, so `exit` + re-`import` still returns the already-loaded module.

**Upgrading a git install**: `pip install 'calcofi4py[viz]'` on an existing install is a no-op
("Requirement already satisfied" — not on PyPI). Re-running the git URL with `--upgrade` is what
moves people forward; verified 0.3.4 → 0.3.5 in a scratch venv on 2026-08-21.

## Changelog (CHANGELOG.md is not optional) — the NEWS.md of this package

- **Every user-facing change bumps the version and gets a bullet in `CHANGELOG.md`, in
  the same commit**: new, changed or removed functions, arguments, defaults, behavior, bug
  fixes, and docs a user reads (articles, README examples). Patch for fixes/docs, minor
  for new functions. Internal churn stays out. Say what changed *for the user* and, when
  it is not obvious, why (the R `NEWS.md` voice — short narrative, not a commit-subject
  dump).
- **Headings are `## <version> (<YYYY-MM-DD>)`, newest first — the date is never omitted.**
  It is the day the version is committed. **There is no "Unreleased" section**: if it is
  on `main`, it has a version and a date (several commits may keep adding bullets under
  the same version until it is tagged). `tests/test_docs.py` fails if the newest heading
  is not `calcofi4py.__version__`, a heading lacks a date, or entries are out of order.
- The site publishes the root file as https://calcofi.io/calcofi4py/changelog/ through
  `hooks/changelog.py` — never copy it into `docs/`.
- Reconstructing a gap retroactively: `git log --format='%h %ad %s' --date=short -G '^version'
  -- pyproject.toml` lists the bump commits with their dates; summarize the commits between
  each pair (`git diff <prev>..<bump> -- src`) and keep the dates from git.

## Secrets and the database — rules that are not negotiable

- **No secret in code, tests, docs, notebooks, or CI.** Passwords live in libpq's
  `~/.pgpass` only; psycopg and DuckDB's postgres extension both read it natively.
- **Do not add database credentials as GitHub secrets.** Docs articles that need the
  database are *pre-rendered locally* (`scripts/render_articles.sh` → committed
  `docs/articles/*.ipynb`, published by mkdocs-jupyter with `execute: false`). The Pages
  build never touches the server, and a compromised workflow cannot reach it.
- **Examples that write must look first, return a handle, and show the undo.** The ledger
  (`ctd.flag`) is append-only by RLS: writers INSERT and may UPDATE only their own
  `proposed` rows to `withdrawn` (`cc_withdraw_flags()`); curators accept/reject; nobody
  deletes. An `INSERT … SELECT` whose WHERE matches nothing inserts nothing and says
  nothing — the README's first example flagged a depth its cast never reached. Execute a
  README example verbatim against the live database before publishing it, and leave no
  `proposed` rows behind (withdraw them).
- Articles and README examples must not change the database: no `cc_propose_flags()`,
  no `write_table=`; show those as code, not executed.

## Testing

Pure-logic tests always run; release tests need the network; PostgreSQL tests are gated
on `CALCOFI_PG_TEST=1` and **open their own tunnel** (never assume one is up — the
original two assumed it and were order-dependent). Write-path tests run inside one
transaction and `rollback()`, so they leave no residue.

## Plotly / MapLibre gotchas (cost a full day)

- `cc_station_map()`: **one** `markers+text` scattermap trace with **string** labels.
  Integer `text` serializes as a binary typed array the symbol layer treats as icon names
  ("Image -15 could not be loaded") and drops the trace; a separate `mode="text"` trace
  never gets its symbol layer in plotly 3.7, so the labels silently vanish.
- `kaleido` and `Plotly.toImage` both fail on scattermap ("Map error"). For a static
  export capture the MapLibre canvas in a `render` event (`m.once('render', …);
  m.triggerRepaint()`) in a *fresh* browser tab.
- Screenshots of WebGL maps are unreliable in both directions; verify map rendering with
  `queryRenderedFeatures()` on the symbol layer, not by eye.
- In static docs (mkdocs-jupyter) display figures as self-contained HTML:
  `HTML(fig.to_html(include_plotlyjs="cdn", full_html=False))`.
- Articles are executed by **jupytext + nbconvert**, not `quarto render --to ipynb`: Quarto
  passes outputs through pandoc, which truncates pandas' `<div><style>…<table>` to `</div>`
  (every DataFrame vanished). DuckDB draws an ipywidgets progress bar per query in Jupyter —
  `SET enable_progress_bar = false` in anything rendered to a static page.
