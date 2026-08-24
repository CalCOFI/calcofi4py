"""Access the public CalCOFI database releases: DuckDB over Parquet on GCS.

Mirrors ``calcofi4r::cc_get_db()`` / ``cc_query()`` (calcofi4r/R/database.R) —
keep the two implementations in step. Releases live at
``gs://calcofi-db/ducklake/releases/{version}/`` and are public: no credentials,
no full download; DuckDB reads only the columns and row groups a query touches.
"""

from __future__ import annotations

import json
import urllib.request

import duckdb

BASE_HTTPS = "https://storage.googleapis.com/calcofi-db/ducklake/releases"
BASE_S3 = "s3://calcofi-db/ducklake/releases"


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (fixed public host)
        return r.read().decode()


def cc_list_versions() -> list[dict]:
    """All published release versions (newest first), from ``versions.json``."""
    return json.loads(_fetch_text(f"{BASE_HTTPS}/versions.json"))["versions"]


def cc_resolve_version(version: str = "latest") -> str:
    """Resolve ``"latest"`` to the promoted version string (e.g. ``v2026.08.14``)."""
    if version == "latest":
        return _fetch_text(f"{BASE_HTTPS}/latest.txt").strip().splitlines()[0]
    if not version.startswith("v"):
        raise ValueError(f"version must be 'latest' or like 'v2026.08.14', got {version!r}")
    return version


def cc_catalog(version: str = "latest") -> dict:
    """The release ``catalog.json``: table names, row counts, partitioned/supplemental flags."""
    version = cc_resolve_version(version)
    return json.loads(_fetch_text(f"{BASE_HTTPS}/{version}/catalog.json"))


def _setup_gcs_httpfs(con: duckdb.DuckDBPyConnection) -> None:
    # anonymous s3-style access to GCS — required for the hive-partitioned globs
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region = 'auto';")
    con.execute("SET s3_endpoint = 'storage.googleapis.com';")
    con.execute("SET s3_url_style = 'path';")
    con.execute("SET s3_access_key_id = '';")
    con.execute("SET s3_secret_access_key = '';")


def cc_get_db(
    version: str = "latest",
    tables: list[str] | None = None,
    supplemental: bool = False,
    con: duckdb.DuckDBPyConnection | None = None,
) -> duckdb.DuckDBPyConnection:
    """DuckDB connection with every release table registered as a view.

    Parameters mirror ``calcofi4r::cc_get_db()``:

    - ``version``: ``"latest"`` (default) or a pinned ``"vYYYY.MM.DD"`` —
      pin for reproducibility, releases are immutable.
    - ``tables``: restrict to these table names (also the way to opt in to a
      single supplemental table by name).
    - ``supplemental``: include the supplemental tables (``obs_ctd_full``
      ~216M rows, ``obs_mets_full`` ~20M) that are hosted + cataloged but
      excluded by default.
    - ``con``: register the views on an existing DuckDB connection (e.g. one
      that already has the PostgreSQL database attached) instead of a new
      in-memory one.

    >>> con = cc_get_db()
    >>> con.sql("SELECT count(*) FROM sample").fetchone()
    """
    version = cc_resolve_version(version)
    catalog = cc_catalog(version)
    if con is None:
        con = duckdb.connect()

    tbls = catalog["tables"]
    if tables is not None:
        tbls = [t for t in tbls if t["name"] in set(tables)]
    elif not supplemental:
        tbls = [t for t in tbls if not t.get("supplemental")]

    if any(t.get("partitioned") for t in tbls):
        _setup_gcs_httpfs(con)
    else:
        con.execute("INSTALL httpfs; LOAD httpfs;")

    for t in tbls:
        name = t["name"]
        if t.get("partitioned"):
            src = (
                f"read_parquet('{BASE_S3}/{version}/parquet/{name}/**/*.parquet',"
                " hive_partitioning = true)"
            )
        else:
            src = f"read_parquet('{BASE_HTTPS}/{version}/parquet/{name}.parquet')"
        con.execute(f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM {src}')

    return con


def cc_query(sql: str, version: str = "latest"):
    """One-shot SQL against a release; returns a ``duckdb`` relation.

    ``cc_query(...).df()`` for a pandas DataFrame, ``.fetchall()`` for tuples.
    """
    return cc_get_db(version).sql(sql)

# quality flags -----------------------------------------------------------------
# ``obs.measurement_qual`` carries each dataset's OWN vocabulary, uninterpreted:
# bottle (6 = ok-from-CTD, 8 = suspect, 9 = missing), CTD cast files (1/2 = use
# primary/secondary sensor, 8 = questionable, 9 = bad or missing), DIC WOCE
# (2 = good, 3 = questionable, 4 = bad, 9 = missing). Nothing downstream applied
# them — the station portal plotted a 1955 bottle oxygen flagged suspect since
# 1955. Documented in CalCOFI/workflows ``metadata/measurement_qual.csv``.
QUAL_EXCLUDE = {
    "calcofi_bottle": ("8", "9"),
    "calcofi_ctd-cast": ("8", "9"),
    "calcofi_dic": ("3", "4", "9"),
}


def qual_ok_sql(alias: str | None = None) -> str:
    """SQL predicate keeping rows whose ``measurement_qual`` is not suspect/bad/missing.

    ``TRUE`` for unflagged rows (NULL), for datasets without a flag vocabulary and
    for codes not in :data:`QUAL_EXCLUDE`; ``FALSE`` otherwise. Bottle codes were
    written ``"8.0"`` through v2026.08.14, so a trailing ``.0`` is stripped first.
    Append to any ``WHERE`` over ``obs``, ``obs_ctd_full``, ``sample_measurement``
    or ``ctd_thin``. Mirrors ``calcofi4r::cc_qual_ok_sql()``.

    >>> con.sql(f"SELECT * FROM obs o WHERE o.dataset_key = 'calcofi_bottle' AND {qual_ok_sql('o')}")
    """
    p = f"{alias}." if alias else ""
    q = f"regexp_replace({p}measurement_qual, '\\.0+$', '')"
    arms = " OR ".join(
        f"({p}dataset_key = '{dk}' AND {q} IN ({', '.join(repr(c) for c in codes)}))"
        for dk, codes in QUAL_EXCLUDE.items()
    )
    # COALESCE: a NULL flag must KEEP the row, and NOT(NULL) is NULL
    return f"COALESCE(NOT ({arms}), TRUE)"
