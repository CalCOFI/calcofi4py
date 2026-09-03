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


def test_catalog_views_listed_named_and_resolved_through_any_reader():
    from calcofi4py import catalog_views, view_sql, view_tables

    cat = fx("catalog_canonical.json")
    views = catalog_views(cat)
    assert list(views) == ["obs"]
    assert view_tables(views["obs"]) == ["obs_bio", "obs_env"]
    assert "{{obs_bio}}" in views["obs"] and "value AS measurement_value" in views["obs"]
    # default: quoted identifiers, as cc_get_db() binds them
    sql = view_sql(cat, "obs")
    assert "{{" not in sql
    assert 'FROM "obs_bio"\nUNION ALL\n' in sql and sql.endswith('FROM "obs_env"')
    # any reader: the catalog's own objects
    sql = view_sql(cat, "obs", lambda t: read_parquet_sql(release_sources(cat, t)))
    assert ("FROM read_parquet('https://storage.googleapis.com/calcofi-db/ducklake/tables/obs_bio/"
            "b19def67a5bcfe2713624ebb/obs_bio.parquet')") in sql
    assert "measurement_type=salinity" in sql and sql.endswith("'], hive_partitioning = true)")
    with pytest.raises(KeyError, match="not a view.*views: obs"):
        view_sql(cat, "nope")
    assert catalog_views(fx("catalog_legacy.json")) == {}
    with pytest.raises(KeyError, match="not a view"):
        view_sql(fx("catalog_legacy.json"), "obs")


def test_deprecated_table_still_resolves_and_view_only_name_raises():
    cat = fx("catalog_canonical.json")
    s = release_sources(cat, "obs")
    assert s["deprecated"] is True and s["replaced_by"] == ["obs_bio", "obs_env"] and s["removed_in"] == "next"
    assert len(s["urls"]) == 2  # its objects ship through the window
    c = release_sources(cat, "cruise")
    assert c["deprecated"] is False and c["replaced_by"] == [] and c["removed_in"] is None
    b = release_sources(cat, "obs_bio")
    assert b["urls"] == [
        "https://storage.googleapis.com/calcofi-db/ducklake/tables/obs_bio/b19def67a5bcfe2713624ebb/obs_bio.parquet"
    ]
    assert b["hive"] is False and b["deprecated"] is False
    e = release_sources(cat, "obs_env")
    assert e["hive"] is True and len(e["urls"]) == 2 and e["single_file"] is None
    # the release after the window: obs is a view alone
    nxt = fx("catalog_view_only.json")
    assert "obs" not in {t["name"] for t in nxt["tables"]}
    with pytest.raises(KeyError, match=r"'obs' is a view in the catalog for v2026.10.01 \(over obs_bio, obs_env\)"):
        release_sources(nxt, "obs")
    with pytest.raises(KeyError, match="not in the catalog"):
        release_sources(nxt, "casts")
    # a legacy catalog has no deprecation fields
    lg = release_sources(fx("catalog_legacy.json"), "obs")
    assert lg["deprecated"] is False and lg["replaced_by"] == [] and lg["removed_in"] is None


# the obs_bio / obs_env pair as tiny local parquet at the fixture catalog's object paths under
# `root`, so the catalog binds offline. Columns are the released ones (calcofi4db build_obs_slim()).
def _write_pair_fixture(root):
    con0 = duckdb.connect()
    cols = ("obs_id, dataset_key, root_id, sample_key, grid_key, cruise_key, latitude, longitude, datetime, year, quarter, "
            "depth_min_m, depth_max_m, depth_bin, taxon_key, life_stage, measurement_type, units, value, measurement_qual, "
            "measurement_prec, qual_ok, tow_type, std_haul_factor, prop_sorted, volume_sampled_m3, density_per_10m2, "
            "density_per_1000m3, effort_class, hex_id, hex7")
    con0.execute(f"""CREATE TABLE obs_bio AS SELECT * FROM (VALUES
      (1::BIGINT, 'swfsc_ichthyo', 1, 'ich:net:1', 'st90-ln90', '2019-04-33UD', 32.9, -117.3, TIMESTAMP '2019-04-02 22:10', 2019::SMALLINT, 2::TINYINT,
       0.0, 210.0, 0, 'worms:217452', 'larva', 'abundance', 'count', 10.0::DOUBLE, NULL::VARCHAR, NULL::DOUBLE, TRUE, 'CB', 2.0, 0.5, 100.0, 40.0, 200.0, 'count_with_effort',
       623333527607443455::UBIGINT, 608870215845019647::UBIGINT)) t({cols})""")
    con0.execute(f"""CREATE TABLE obs_env AS SELECT * FROM (VALUES
      (2::BIGINT, 'calcofi_bottle', 2, 'btl:b:1', 'st90-ln90', '2019-04-33UD', 32.9, -117.3, TIMESTAMP '2019-04-02 23:00', 2019::SMALLINT, 2::TINYINT,
       10.0, 10.0, 10, NULL::VARCHAR, NULL::VARCHAR, 'temperature', 'degC', 15.5::DOUBLE, '6', NULL::DOUBLE, TRUE, NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, 'other_unit',
       623333527607443455::UBIGINT, 608870215845019647::UBIGINT),
      (3::BIGINT, 'calcofi_bottle', 2, 'btl:b:1', 'st90-ln90', '2019-04-33UD', 32.9, -117.3, TIMESTAMP '2019-04-02 23:00', 2019::SMALLINT, 2::TINYINT,
       10.0, 10.0, 10, NULL::VARCHAR, NULL::VARCHAR, 'salinity', 'psu', 33.4::DOUBLE, '6', NULL::DOUBLE, TRUE, NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, 'other_unit',
       623333527607443455::UBIGINT, 608870215845019647::UBIGINT)) t({cols})""")

    def mk(rel):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    con0.execute(f"COPY obs_bio TO '{mk('ducklake/tables/obs_bio/b19def67a5bcfe2713624ebb/obs_bio.parquet')}' (FORMAT parquet)")
    # the env partitions are written WITHOUT the partition column, as the release writer does
    for mt, h in (("salinity", "4444444444444444444444dd"), ("temperature", "5555555555555555555555ee")):
        con0.execute(f"COPY (SELECT * EXCLUDE (measurement_type) FROM obs_env WHERE measurement_type = '{mt}') "
                     f"TO '{mk(f'ducklake/tables/obs_env/measurement_type={mt}/{h}/data_0.parquet')}' (FORMAT parquet)")
    con0.execute(f"COPY (SELECT 'x' AS cruise_key UNION ALL SELECT 'y') TO '{mk('ducklake/tables/cruise/a1b2c3d4e5f60718293a4b5c/cruise.parquet')}' (FORMAT parquet)")
    # the deprecated obs's own objects, a different shape on purpose: they must not be read
    for rel in ("ducklake/tables/obs/year=2019/1111111111111111111111aa/data_0.parquet",
                "ducklake/tables/obs/year=2020/2222222222222222222222bb/data_0.parquet",
                "ducklake/tables/obs/9999999999999999999999ff/obs.parquet"):
        con0.execute(f"COPY (SELECT 1 AS legacy_obs) TO '{mk(rel)}' (FORMAT parquet)")
    con0.close()


def _views_of(con):
    return {r[0] for r in con.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}


def test_register_catalog_serves_obs_as_the_view_over_the_pair_offline(tmp_path):
    from calcofi4py.release import _register_catalog

    _write_pair_fixture(tmp_path)
    cat = fx("catalog_canonical.json")
    con = _register_catalog(duckdb.connect(), cat, base_https=str(tmp_path))
    # the default set: obs_bio and obs_env are core, obs_ctd_full supplemental, obs the view
    assert _views_of(con) == {"cruise", "obs", "obs_bio", "obs_env"}
    cols = [d[0] for d in con.sql("SELECT * FROM obs").description]
    assert cols == ["obs_id", "realm", "dataset_key", "sample_key", "grid_key", "cruise_key", "latitude", "longitude",
                    "datetime", "depth_min_m", "depth_max_m", "taxon_key", "life_stage", "measurement_type",
                    "measurement_value", "measurement_qual", "measurement_prec", "hex_id"]
    rows = con.sql("SELECT obs_id, realm, measurement_type, measurement_value, sample_key FROM obs ORDER BY obs_id").fetchall()
    assert rows == [(1, "bio", "abundance", 10.0, "ich:net:1"), (2, "env", "temperature", 15.5, "btl:b:1"),
                    (3, "env", "salinity", 33.4, "btl:b:1")]
    # tables=['obs'] pulls the pair in; the deprecated objects are never bound
    con2 = _register_catalog(duckdb.connect(), cat, tables=["obs"], base_https=str(tmp_path))
    assert _views_of(con2) == {"obs", "obs_bio", "obs_env"}
    assert con2.sql("SELECT count(*) FROM obs").fetchone()[0] == 3
    # the release after the window: no obs table, the view still answers
    con3 = _register_catalog(duckdb.connect(), fx("catalog_view_only.json"), base_https=str(tmp_path))
    assert _views_of(con3) == {"cruise", "obs", "obs_bio", "obs_env"}
    assert con3.sql("SELECT count(*) FROM obs WHERE realm = 'env'").fetchone()[0] == 2
    # a catalog without views binds exactly as before
    plain = {"version": "v1", "tables": [t for t in cat["tables"] if t["name"] == "cruise"]}
    con4 = _register_catalog(duckdb.connect(), plain, base_https=str(tmp_path))
    assert _views_of(con4) == {"cruise"}


def test_retired_version_raises_naming_replacement():
    from calcofi4py.release import RetiredVersionError, _raise_if_retired

    versions = [{"version": "v2026.05.15", "retired": {"retired_utc": "2026-09-01T00:00:00Z", "to": "v2026.06.26"}},
                {"version": "v2026.06.26"}]
    with pytest.raises(RetiredVersionError, match="retired on 2026-09-01.*v2026.06.26") as e:
        _raise_if_retired("v2026.05.15", versions)
    assert e.value.to == "v2026.06.26"
    _raise_if_retired("v2026.06.26", versions)  # kept: no error
