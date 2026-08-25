"""release_sources() — the fixtures are shared byte-for-byte with calcofi4r/tests/testthat/fixtures/."""
import json
from pathlib import Path

import duckdb
import pytest

from calcofi4py import read_parquet_sql, release_sources

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return json.loads((FX / name).read_text())


def test_canonical_resolves_to_content_addressed_objects():
    cat = fx("catalog_canonical.json")
    s = release_sources(cat, "cruise")
    assert s["urls"] == [
        "https://storage.googleapis.com/calcofi-db/ducklake/tables/cruise/a1b2c3d4e5f60718293a4b5c/cruise.parquet"
    ]
    assert s["hive"] is False and s["canonical"] is True
    assert s["hashes"] == ["a1b2c3d4e5f60718293a4b5c6d7e8f90"]
    assert s["local_paths"] == ["tables/cruise/a1b2c3d4e5f60718293a4b5c/cruise.parquet"]

    s = release_sources(cat, "obs")
    assert s["urls"] == [
        "https://storage.googleapis.com/calcofi-db/ducklake/tables/obs/year=2019/1111111111111111111111aa/data_0.parquet",
        "https://storage.googleapis.com/calcofi-db/ducklake/tables/obs/year=2020/2222222222222222222222bb/data_0.parquet",
    ]
    assert s["hive"] is True
    # the single-file twin is exposed separately, never mixed into the partition list
    assert s["single_file"] == (
        "https://storage.googleapis.com/calcofi-db/ducklake/tables/obs/9999999999999999999999ff/obs.parquet"
    )
    assert release_sources(cat, "cruise")["single_file"] is None
    sql = read_parquet_sql(s)
    assert sql.startswith("read_parquet(['https") and sql.endswith("'], hive_partitioning = true)")
    assert read_parquet_sql(release_sources(cat, "cruise")) == (
        "read_parquet('https://storage.googleapis.com/calcofi-db/ducklake/tables/cruise/"
        "a1b2c3d4e5f60718293a4b5c/cruise.parquet')"
    )
    with pytest.raises(KeyError):
        release_sources(cat, "nope")


def test_legacy_resolves_to_per_release_paths():
    cat = fx("catalog_legacy.json")
    s = release_sources(cat, "cruise")
    assert s["urls"] == [
        "https://storage.googleapis.com/calcofi-db/ducklake/releases/v2026.08.14/parquet/cruise.parquet"
    ]
    assert s["canonical"] is False and s["hashes"] == [None]
    s = release_sources(cat, "obs")
    assert s["urls"] == ["s3://calcofi-db/ducklake/releases/v2026.08.14/parquet/obs/**/*.parquet"]
    assert s["hive"] is True
    assert s["single_file"] == "https://storage.googleapis.com/calcofi-db/ducklake/releases/v2026.08.14/parquet/obs.parquet"


def test_duckdb_recovers_partition_column_from_canonical_style_list(tmp_path):
    con = duckdb.connect()
    files = []
    for y in (2019, 2020):
        d = tmp_path / "obs" / f"year={y}" / f"hash{y}"
        d.mkdir(parents=True)
        f = d / "data_0.parquet"
        con.execute(f"COPY (SELECT {y} + i AS id, 1.5 AS v FROM range(2) t(i)) TO '{f}' (FORMAT parquet)")
        files.append(str(f))
    sql = read_parquet_sql({"urls": files, "hive": True})
    got = con.sql(f"SELECT year, count(*) FROM {sql} GROUP BY year ORDER BY year").fetchall()
    # the {hash} directory between key=value and the file is not a hive segment
    assert got == [(2019, 2), (2020, 2)]


def test_retired_version_raises_naming_replacement():
    from calcofi4py.release import RetiredVersionError, _raise_if_retired

    versions = [{"version": "v2026.05.15", "retired": {"retired_utc": "2026-09-01T00:00:00Z", "to": "v2026.06.26"}},
                {"version": "v2026.06.26"}]
    with pytest.raises(RetiredVersionError, match="retired on 2026-09-01.*v2026.06.26") as e:
        _raise_if_retired("v2026.05.15", versions)
    assert e.value.to == "v2026.06.26"
    _raise_if_retired("v2026.06.26", versions)  # kept: no error
