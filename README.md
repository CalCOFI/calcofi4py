# calcofi4py <img src="https://calcofi.io/calcofi4py/assets/logo.svg" align="right" width="130" alt="calcofi4py logo"/>

CalCOFI Python helpers — the thin sibling of [calcofi4r](https://calcofi.io/calcofi4r).
Two data stores, a few verbs, no credentials in code.

```bash
pip install "calcofi4py @ git+https://github.com/CalCOFI/calcofi4py"
```

## The public database releases (no account needed)

Immutable, versioned Parquet on a public bucket; DuckDB reads only what a query
touches, straight over HTTPS.

```python
import calcofi4py as cc

con = cc.cc_get_db()                       # latest release, every table as a view
con.sql("SHOW TABLES")
df = con.sql("""
  SELECT date_trunc('year', s.datetime_utc) AS year, count(*) AS casts
  FROM sample s WHERE s.dataset_key = 'calcofi_ctd-cast'
  GROUP BY 1 ORDER BY 1
""").df()

cc.cc_query("SELECT count(*) FROM obs").fetchone()      # one-shot
cc.cc_get_db("v2026.08.14")                             # pin a version (reproducible)
cc.cc_get_db(supplemental=True)                         # + obs_ctd_full (216M rows), obs_mets_full
cc.cc_list_versions()[:3]
```

To see what's in each table first: the [Schema explorer](https://calcofi.io/db-schema/).
More: [Data Access](https://calcofi.io/docs/data-access.html).

## The CTD team's PostgreSQL working database (account required)

Private, multi-user, reached over SSH — see
[Server Access](https://calcofi.io/docs/server-access.html) for the account,
the `~/.ssh/config` alias `calcofi`, and the `~/.pgpass` file (your password
lives there and in no script, ever).

```python
import calcofi4py as cc

con = cc.cc_pg_connect(tunnel=True)        # opens `ssh -N calcofi` for you; ~/.pgpass auth
con.execute("SELECT count(*) FROM ctd.cast WHERE is_best_stage").fetchone()

casts = cc.cc_ctd_casts(con, "2304SH")                                  # one row per cast (best stage)
scans = cc.cc_ctd_scans(con, "2304SH", cast_id="2304_001d",
                        columns=["temp1", "temp2"])                     # this cast: 40 scans, 3–42 m, 1 m bins

# propose a QC flag — look first, write second, and you can still undo
where, args = "study = %s AND cast_id = %s AND depth = %s", ("2304SH", "2304_001d", 20)

hit = con.execute(f"SELECT scan_id, depth, temp1, temp2 FROM ctd.v_scan_best WHERE {where}", args).fetchall()
assert len(hit) == 1, hit             # [] = your WHERE matches nothing, and the INSERT below would flag nothing, silently

(flag_id,) = con.execute(f"""
  INSERT INTO ctd.flag (scan_id, variable, qual_code, reason)
  SELECT scan_id, 'temp1', 3, 'README example (withdrawn right after)'
  FROM ctd.v_scan_best WHERE {where}
  RETURNING flag_id
""", args).fetchone()
con.commit()                          # con.rollback() instead discards it before anyone sees it

cc.cc_flags(con, "2304SH", status="proposed")     # the ledger: who proposed what, and its fate

# undo: the ledger is append-only, so undo = withdraw your own proposal (the audit trail keeps it);
# curators accept/reject everything else in pgAdmin or SQL
cc.cc_withdraw_flags(con, [flag_id], note="README example")
cc.cc_pg_tunnel_close()
```

### Both at once — release Parquet ⋈ PostgreSQL in one DuckDB query

```python
con = cc.cc_get_db(tables=["cruise", "sample"])
cc.cc_pg_attach(con)                       # ATTACH ... AS pg (through your tunnel)
con.sql("""
  SELECT f.study, f.cruise_key, count(*) AS flags
  FROM pg.ctd.flag f GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10
""")
```

## Conventions inherited from calcofi4r (do not drift)

- Secrets only in `~/.pgpass` / `%APPDATA%\postgresql\pgpass.conf`; never a
  password argument in examples.
- `PGHOST` / `PGPORT` / `PGUSER` override every default; on the CalCOFI server
  the host defaults to `postgis` (no tunnel), elsewhere `localhost`.
- Release access follows `catalog.json` exactly: `partitioned` tables are
  s3-glob views with `hive_partitioning`, `supplemental` tables opt-in.

## Dev

```bash
pip install -e ".[dev]"
pytest -q                       # pure-logic + (if online) release tests
CALCOFI_PG_TEST=1 pytest -q     # + live PostgreSQL tests (tunnel + ~/.pgpass)
```
