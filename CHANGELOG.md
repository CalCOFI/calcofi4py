# Changelog

User-facing changes per version, newest first — new, changed or removed functions,
arguments, defaults, behavior, fixes, and docs a user reads. Dates are the commit dates
on `main`. From 0.3.5 on every version is also a git tag, so it can be pinned:
`pip install "calcofi4py[viz] @ git+https://github.com/CalCOFI/calcofi4py@vX.Y.Z"`
(earlier versions only by commit SHA). `calcofi4py.__version__` tells you which one
you have. The R sibling's history is at https://calcofi.io/calcofi4r/news/.

## 0.4.0 (2026-08-25)

Content-addressed releases (mirrors calcofi4r 1.11.0).

- New `release_sources(catalog, table)` and `read_parquet_sql(src)`: the one place a
  release table becomes parquet URLs. From the v2026.09 releases each table/partition is
  an immutable object under `gs://calcofi-db/ducklake/tables/{table}/{content_hash}/…`
  listed in the catalog's `objects[]`; earlier catalogs still resolve to their
  per-release `releases/{version}/parquet/…` paths, which from now on are only
  guaranteed for the promoted and consolidated versions — never build one by hand.
- `cc_get_db()` resolves tables through `release_sources()`; partitioned tables on a
  canonical release are read as an explicit https file list with
  `hive_partitioning = true` (no anonymous-S3 glob).
- Tests share `tests/fixtures/catalog_*.json` byte-for-byte with calcofi4r.

## 0.3.7 (2026-08-24)

- New `qual_ok_sql(alias=None)` and `QUAL_EXCLUDE`: the `WHERE` predicate that drops
  suspect/bad/missing `measurement_qual` codes per dataset (bottle 8/9, CTD 8/9, DIC
  3/4/9), mirroring `calcofi4r::cc_qual_ok_sql()`.

## 0.3.6 (2026-08-21)

Docs and tooling — no API change.

- Article [CTD QA/QC, end to end](https://calcofi.io/calcofi4py/articles/ctd-qaqc/) —
  the R-vignette equivalent: casts → map → QC rules → triage → ledger → clean 1 m bins →
  a cross-store query → session info, on one cruise × one variable, read-only.
  Pre-rendered locally by someone with an account (`scripts/render_articles.sh`), so the
  site build holds no database credentials.
- This changelog, published at https://calcofi.io/calcofi4py/changelog/ straight from the
  repo-root `CHANGELOG.md` (`hooks/changelog.py`); `tests/test_docs.py` fails when the
  newest entry is not the installed version or a version heading has no date. Every
  change on `main` gets a version and a date — there is no "unreleased" section.
- The site header, page titles and every example show the documented version
  (`hooks/version.py`; `tests/test_docs.py` fails if README/docs quote a stale one).
- Install line is `calcofi4py[viz]` — every example needs pandas + plotly. How to upgrade
  (`pip install --upgrade` with the git URL; a bare `pip install 'calcofi4py[viz]'` is a
  no-op on an existing install) and how to pin (`@vX.Y.Z`).
- README *Both at once*: what the two stores are, why `cruise_key` joins them, how DuckDB
  bridges them; the broken example query (`ctd.flag` has no `study`/`cruise_key`) replaced
  by a verified flag-ledger ⋈ release-sample join.
- `scripts/deploy_server.sh` — upgrades the copy baked into rstudio.calcofi.io after a
  release (the examples are run there through reticulate).

## 0.3.5 (2026-08-21)

- New `cc_withdraw_flags(con, flag_ids, note=None, commit=True)` — the undo. The ledger
  (`ctd.flag`) is append-only: a withdrawn proposal stays in the ledger and in
  `ctd.flag_audit`. Only your own still-`proposed` flags are affected (curators may
  withdraw anyone's); accepted or rejected flags are a curator decision, left untouched
  and not counted in the returned number.
- README / docs flag example fixed. It now looks first (`assert len(hit) == 1` — an
  `INSERT … SELECT` whose `WHERE` matches nothing inserts nothing and says nothing; the
  old example flagged a depth its cast never reached), keeps the `RETURNING flag_id`
  handle, shows the ledger with `cc_flags(…, status="proposed")`, and withdraws the flag.
  Executed verbatim against the live database before publishing.
- First git tag, `v0.3.5`; `tests/test_pg_live.py` covers propose → withdraw inside a
  rolled-back transaction.

## 0.3.4 (2026-08-20)

- Flagged scans in `cc_profile_plot()` and `cc_profile_explorer()` are drawn violet
  (`#9467bd`) instead of crimson — flags should stand out, not alarm.

## 0.3.3 (2026-08-20)

- Fix `cc_station_map()`: the `cast_seq` labels are back. 0.3.2 had split markers and
  labels into two traces, and plotly 3.7 never creates the symbol layer for a text-only
  scattermap trace, so the numbers silently vanished. Back to **one** `markers+text`
  trace with **string** labels — the one configuration that renders.
- Docs site: dark by default (light one toggle away), calcofi4py logo (calcofi4r's
  navy + yellow palette), API reference grouped under section headings with short names.

## 0.3.2 (2026-08-20)

- New `cc_session_info(packages=…, repos=None, extra=None)` — the Python
  `devtools::session_info()`, as printable text for the tail of a QA/QC notebook whose
  rendered HTML is the archive of a cleaning run: Python, platform, package versions
  (`calcofi4py` first), and the last git commit touching each data-rule path you name
  (`repos={"qc_rules": (repo, "metadata/qc_rules")}`), with a dirty-tree warning so an
  uncommitted rule change cannot masquerade as a committed one.
- `cc_station_map()` gains `zoom=` (default 4.7 — the CalCOFI grid fits) and centers on
  the casts. It also moved markers and labels into separate traces, which dropped the
  labels; reverted in 0.3.3.

## 0.3.1 (2026-08-20)

- Fix `cc_station_map()` rendering an **empty map**: integer `text` serialized as
  plotly's binary typed array, which plotly.js drops for `text`; labels are now strings.
- `cc_profile_explorer()`: the cast dropdown moved top-left, out from under the modebar
  that appears on hover at the top-right (it was unclickable there); title centered.

## 0.3.0 (2026-08-20)

`cast_seq` everywhere — the cast number shared by a down/up pair (`"2607_001d"` → 1) is
now the key that cross-references every table and figure.

- `cc_ctd_casts()` and `cc_ctd_scans()` return a `cast_seq` column.
- `cc_flags()` exposes `scan_id`, so the ledger joins back to scans.
- `cc_station_map()`: one labeled marker per station occupation (the down + up pair
  collapsed to one point, downcast position preferred) labeled with its `cast_seq`;
  hover carries station, time, directions, scan counts and max depth. **Removed** the
  `color=` argument (was `"cast_dir"`).
- `cc_section_plot()`: the x axis is `cast_seq` (was a time-ordered cast index).
- New `cc_profile_explorer(scans, column="tempave", flags=None, units="", title=None,
  default="all")` — depth profiles with a dropdown per `cast_seq` ("all casts" + each
  occupation), flagged scans overlaid on the selected cast.
- New `cc_flag_summary(ledger, scans, column)` — flags rolled up per `cast_seq`, the
  triage table: `n_flags`, per-`rule_key` counts, depth and value spans,
  `pct_scans_flagged`; sorted so the casts that most need a human are on top.

## 0.2.0 (2026-08-20)

CTD QA/QC module (`calcofi4py.ctd`) against the `ctd` schema of the PostgreSQL working
database, and a new `[viz]` extra (pandas + plotly).

- Readers: `cc_ctd_casts(con, study, best_only=True)` — one row per physical cast;
  `cc_ctd_scans(con, study, columns=("tempave", "salt1", "ox1"), cast_id=None, qc=True)`
  — scan-level data from `ctd.v_scan_qc`, each column with its accepted `_qc` flag and
  `_fix` value.
- Portable QC rules returning candidate scans: `cc_qc_spike()` (deviation from the
  neighbours' midpoint *while* the neighbours agree — otherwise every thermocline
  gradient fires), `cc_qc_sensor_pair()` (primary vs secondary sensor disagreement),
  `cc_qc_range()` (outside declared physical bounds).
- The flag ledger: `cc_propose_flags()` — idempotent, a scan already carrying a
  proposed/accepted flag for that variable is skipped, so re-running a notebook does not
  stack duplicates; `cc_flags()` — the ledger joined to its scans (who proposed what,
  where, and its fate).
- Clean products: `cc_bin_1m()` — 1 m binned averages per cast from `ctd.v_scan_clean`
  (accepted fixes substituted, accepted-bad values NULLed); `write_table=` also writes
  `work.<name>` so colleagues can query it by name.
- Plotly viz: `cc_station_map()`, `cc_profile_plot()` (with `flags=` overlay),
  `cc_section_plot()`.
- Docs site at https://calcofi.io/calcofi4py/ — mkdocs-material + mkdocstrings (the
  Python pkgdown), deployed to gh-pages on every push to `main`.

## 0.1.0 (2026-08-20)

First release: the thin Python sibling of [calcofi4r](https://calcofi.io/calcofi4r) —
same verbs, same defaults, same conventions (`cc_*` names, secrets only in `~/.pgpass`,
`PGHOST`/`PGPORT`/`PGUSER` override).

- Public database releases (DuckDB over Parquet on GCS, no credentials):
  `cc_get_db(version="latest", tables=None, supplemental=False, con=None)` — a DuckDB
  connection with every release table as a view, following `catalog.json` exactly;
  `cc_query(sql, version="latest")` for one-shots; `cc_list_versions()`,
  `cc_catalog()`, `cc_resolve_version()`.
- The CTD team's PostgreSQL working database (private, over SSH):
  `cc_pg_connect(dbname="calcofi", host=None, port=None, user=None, tunnel=False)` —
  psycopg with every default resolved (`postgis` on the server, `localhost` elsewhere;
  role from `~/.pgpass`; password never passed, libpq reads it);
  `cc_pg_tunnel()` / `cc_pg_tunnel_close()` — background `ssh -N` via your
  `~/.ssh/config` alias, reused while alive, an already-occupied port is left alone
  (use `local_port=15432`); `cc_pg_attach()` — the PostgreSQL database inside a DuckDB
  connection so release Parquet and `pg.ctd.*` join in one query; `cc_pgpass_user()`,
  `cc_on_server()`.
