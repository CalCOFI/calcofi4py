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

# ---------------------------------------------------------------------------------------------
# Effort and denominators (plan D8, 2026-08-28). A bio observation is a count, a count with the
# effort that produced it, or a density a provider already standardized — not one population.
#   density_per_10m2   areal, depth-integrated: count * std_haul_factor / prop_sorted for oblique and
#                      vertical tows (C1, CB, CV, PV — never the surface manta MT); published per-m2 * 10
#   density_per_1000m3 volumetric: count / prop_sorted / volume_sampled_m3 * 1000 for any tow with a
#                      volume; published per-1000 m3 densities as is
#   effort_class       count_with_effort | raw_count_no_effort | density_as_published | other_unit
# Areal and volumetric are deliberately NOT converted into each other. The expression is the same
# bytes as calcofi4r::cc_density_sql() and the explorer's sql/density.sql; tests/fixtures pins it.
DENSITY_UNITS = {"area": ("count/m2", "numberPerMeterSquared"), "volume": ("count/1000m3",)}
AREAL_GEARS = ("C1", "CB", "CV", "PV")


def density_sql(
    alias: str | None = None,
    value: str = "measurement_value",
    units: str = "units",
    tow_type: str = "tow_type",
    std_haul_factor: str = "std_haul_factor",
    prop_sorted: str = "prop_sorted",
    volume_sampled_m3: str = "volume_sampled_m3",
    as_select: bool = True,
) -> str | dict[str, str]:
    """SQL deriving ``density_per_10m2``, ``density_per_1000m3`` and ``effort_class``.

    Returns one ``SELECT``-list fragment of three ``expr AS name`` clauses (``as_select=True``),
    or the three bare expressions keyed by column name. Byte-identical to
    ``calcofi4r::cc_density_sql()``.
    """
    p = f"{alias}." if alias else ""
    v, u, tt = p + value, p + units, p + tow_type
    shf, ps, vol = p + std_haul_factor, p + prop_sorted, p + volume_sampled_m3
    q = lambda xs: ", ".join(f"'{x}'" for x in xs)  # noqa: E731
    sorted_ = f"COALESCE(NULLIF({ps}, 0), 1)"  # 0 or NULL prop_sorted = all of it was sorted
    ex = {
        "density_per_10m2": (
            f"CASE WHEN {u} = 'count' AND {shf} IS NOT NULL AND {tt} IN ({q(AREAL_GEARS)}) THEN {v} * {shf} / {sorted_}\n"
            f"     WHEN {u} IN ({q(DENSITY_UNITS['area'])}) THEN {v} * 10\n     END"),
        "density_per_1000m3": (
            f"CASE WHEN {u} = 'count' AND {vol} IS NOT NULL AND {vol} > 0 THEN {v} / {sorted_} / {vol} * 1000\n"
            f"     WHEN {u} IN ({q(DENSITY_UNITS['volume'])}) THEN {v}\n     END"),
        "effort_class": (
            f"CASE WHEN {u} = 'count' AND {shf} IS NULL AND {vol} IS NULL THEN 'raw_count_no_effort'\n"
            f"     WHEN {u} = 'count' THEN 'count_with_effort'\n"
            f"     WHEN {u} IN ({q(DENSITY_UNITS['area'] + DENSITY_UNITS['volume'])}) THEN 'density_as_published'\n"
            f"     ELSE 'other_unit' END"),
    }
    if not as_select:
        return ex
    return ",\n".join(f"{e} AS {k}" for k, e in ex.items())


def default_stage(picker: list[dict]) -> str | None:
    """The life stage a taxon opens on: most rows carrying effort, tie -> most rows (D8 rule 4).

    ``picker`` rows carry ``dataset_key, life_stage, n, n_10m2, n_1000m3`` (one per dataset x stage).
    Eggs and larvae are never merged; ``None`` is a stage of its own.
    """
    if not picker:
        return None
    eff: dict = {}
    n: dict = {}
    for r in picker:
        k = r.get("life_stage")
        eff[k] = eff.get(k, 0) + max(r["n_10m2"], r["n_1000m3"])
        n[k] = n.get(k, 0) + r["n"]
    return sorted(eff, key=lambda k: (-eff[k], -n[k], k or ""))[0]


def default_denominator(picker: list[dict], stage: str | None) -> str:
    """The denominator covering the most datasets *with effort* for this stage — never largest-n.

    ``per_10m2`` on a tie (areal, depth-integrated is the CalCOFI convention); ``raw`` only when
    nothing carries effort, and the caller labels it as not comparable across gear or datasets.
    """
    rows = [r for r in picker if r.get("life_stage") == stage]
    ds10 = {r["dataset_key"] for r in rows if r["n_10m2"] > 0}
    ds1000 = {r["dataset_key"] for r in rows if r["n_1000m3"] > 0}
    if not ds10 and not ds1000:
        return "raw"
    return "per_1000m3" if len(ds1000) > len(ds10) else "per_10m2"
