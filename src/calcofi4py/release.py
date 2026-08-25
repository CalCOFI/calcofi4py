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
    _raise_if_retired(version)
    return version


class RetiredVersionError(LookupError):
    """The version's parquet was removed by archive thinning; ``.to`` names the replacement."""

    def __init__(self, version: str, retired: dict):
        self.version, self.to = version, retired.get("to")
        super().__init__(
            f"Release {version} was retired on {str(retired.get('retired_utc', ''))[:10]}: its parquet "
            f"was removed from the archive (its notes and catalog remain). Use version={self.to!r} — "
            "the nearest consolidated release — or 'latest'. See cc_list_versions()."
        )


def _raise_if_retired(version: str, versions: list[dict] | None = None) -> None:
    # a thinned version keeps its sidecars but its parquet is gone (CalCOFI/workflows
    # metadata/release_policy.yml); say so up front instead of failing per table on 404s
    if versions is None:
        try:
            versions = cc_list_versions()
        except Exception:  # noqa: BLE001 — offline: let the real fetch report
            return
    for r in versions:
        if r.get("version") == version and r.get("retired"):
            raise RetiredVersionError(version, r["retired"])


def cc_catalog(version: str = "latest") -> dict:
    """The release ``catalog.json``: table names, row counts, partitioned/supplemental flags."""
    version = cc_resolve_version(version)
    return json.loads(_fetch_text(f"{BASE_HTTPS}/{version}/catalog.json"))


BUCKET_HTTPS = "https://storage.googleapis.com/calcofi-db"


def release_sources(catalog: dict, table: str, base_https: str = BUCKET_HTTPS) -> dict:
    """Where a release table's parquet bytes live. Mirrors ``calcofi4r::cc_release_sources()``.

    Since the v2026.09 releases the database is content-addressed: each table (or
    partition) is one immutable object under ``ducklake/tables/{table}/{hash}/…``,
    listed per table in the catalog's ``objects[]``. Rules, in order:

    1. entry has ``objects[]`` → one https URL per object, in catalog order
       (partition files carry their ``key=value`` segment, so DuckDB's
       ``hive_partitioning=true`` recovers the partition column);
    2. otherwise (releases before v2026.09) → the legacy per-release path, or an
       ``s3://`` glob for a partitioned table (DuckDB cannot glob over https).

    Returns ``{"urls", "hive", "canonical", "hashes", "local_paths", "single_file"}``;
    ``local_paths`` mirror the bucket layout so a cache is content-addressed;
    ``single_file`` is the whole-table file a partitioned table may also publish
    (``obs`` does) for https-only readers — read it *or* ``urls``, never both.
    Never build a ``releases/{version}/parquet/…`` path by hand: it is only
    guaranteed to answer for the promoted and consolidated versions.
    """
    entry = next((t for t in catalog["tables"] if t["name"] == table), None)
    if entry is None:
        raise KeyError(f"table {table!r} is not in the catalog for {catalog.get('version')}")
    partitioned = bool(entry.get("partitioned"))
    version = catalog["version"]
    objs = entry.get("objects") or []
    if objs:
        single_file = None
        if partitioned:
            # a partitioned table may ALSO publish one whole-table file (obs does,
            # for browser DuckDB-WASM and other https-only readers that cannot
            # take a list): the object without a partition. Never read it
            # alongside the partitions — that would double every row.
            twins = [o for o in objs if "partition_by" not in o]
            objs = [o for o in objs if "partition_by" in o]
            if twins:
                single_file = f"{base_https}/{twins[0]['path']}"
        paths = [o["path"] for o in objs]
        return {
            "urls": [f"{base_https}/{p}" for p in paths],
            "hive": partitioned,
            "canonical": True,
            "hashes": [o.get("content_hash") for o in objs],
            "local_paths": [p.removeprefix("ducklake/") for p in paths],
            "single_file": single_file,
        }
    if partitioned:
        return {
            "urls": [f"s3://calcofi-db/ducklake/releases/{version}/parquet/{table}/**/*.parquet"],
            "hive": True, "canonical": False, "hashes": [None], "local_paths": [None],
            # obs is the one legacy partitioned table with a single-file twin
            "single_file": (f"{base_https}/ducklake/releases/{version}/parquet/obs.parquet"
                            if table == "obs" else None),
        }
    return {
        "urls": [f"{base_https}/ducklake/releases/{version}/parquet/{table}.parquet"],
        "hive": False, "canonical": False, "hashes": [None],
        "local_paths": [f"releases/{version}/parquet/{table}.parquet"],
        "single_file": None,
    }


def read_parquet_sql(src: dict, paths: list[str] | None = None) -> str:
    """The ``read_parquet(...)`` SQL for a resolved source (mirrors ``cc_read_parquet_sql()``)."""
    paths = list(src["urls"] if paths is None else paths)
    lst = f"'{paths[0]}'" if len(paths) == 1 else "[" + ", ".join(f"'{p}'" for p in paths) + "]"
    return f"read_parquet({lst}, hive_partitioning = true)" if src["hive"] else f"read_parquet({lst})"


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

    srcs = {t["name"]: release_sources(catalog, t["name"]) for t in tbls}
    # a legacy partitioned table is an s3:// glob and needs the anonymous-S3
    # settings; canonical objects are plain https
    if any(u.startswith("s3://") for s in srcs.values() for u in s["urls"]):
        _setup_gcs_httpfs(con)
    else:
        con.execute("INSTALL httpfs; LOAD httpfs;")

    for name, src in srcs.items():
        con.execute(f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM {read_parquet_sql(src)}')

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
