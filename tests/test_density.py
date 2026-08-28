"""density_sql() is one set of bytes in three runtimes: tests/fixtures/density_sql.txt is shared
byte-for-byte with calcofi4r/tests/testthat/fixtures/density_sql.txt and CalCOFI/explore/sql/density.sql."""
from pathlib import Path

import duckdb

from calcofi4py import default_denominator, default_stage, density_sql

FX = Path(__file__).parent / "fixtures" / "density_sql.txt"


def test_density_sql_matches_shared_fixture():
    assert density_sql() == FX.read_text().rstrip("\n")
    assert list(density_sql(as_select=False)) == ["density_per_10m2", "density_per_1000m3", "effort_class"]
    assert "o.measurement_value * o.std_haul_factor" in density_sql("o")


def test_density_sql_rule_2():
    con = duckdb.connect()
    con.execute("""CREATE TABLE obs AS SELECT * FROM (VALUES
        (1, 10.0, 'count', 'C1', 2.0, 0.5, 100.0),
        (2, 10.0, 'count', 'MT', 2.0, 0.5, 100.0),
        (3, 10.0, 'count', NULL, NULL, NULL, NULL),
        (4, 10.0, 'count', 'CB', 3.0, 0.0, NULL),
        (5, 5.0, 'count/m2', NULL, NULL, NULL, NULL),
        (6, 7.0, 'count/1000m3', NULL, NULL, NULL, NULL),
        (7, 3.0, 'mgC/m2', NULL, NULL, NULL, NULL),
        (8, 4.0, 'numberPerMeterSquared', NULL, NULL, NULL, NULL),
        (9, 8.0, 'count', 'PV', 1.5, NULL, 0.0)
      ) t(id, measurement_value, units, tow_type, std_haul_factor, prop_sorted, volume_sampled_m3)""")
    rows = con.execute(f"SELECT id, {density_sql()} FROM obs ORDER BY id").fetchall()
    d = {r[0]: r[1:] for r in rows}
    assert d[1] == (40.0, 200.0, "count_with_effort")      # oblique: areal + volumetric
    assert d[2] == (None, 200.0, "count_with_effort")      # manta: never areal
    assert d[3] == (None, None, "raw_count_no_effort")
    assert d[4] == (30.0, None, "count_with_effort")       # prop_sorted 0 = all sorted
    assert d[5] == (50.0, None, "density_as_published")
    assert d[6] == (None, 7.0, "density_as_published")
    assert d[7] == (None, None, "other_unit")
    assert d[8] == (40.0, None, "density_as_published")
    assert d[9] == (12.0, None, "count_with_effort")       # volume 0 is not a volume


def test_picker_defaults_rule_4():
    p = [
        {"dataset_key": "swfsc_ichthyo", "life_stage": "larva", "n": 7420, "n_10m2": 6158, "n_1000m3": 7420},
        {"dataset_key": "swfsc_ichthyo", "life_stage": "egg", "n": 5906, "n_10m2": 4907, "n_1000m3": 5906},
        {"dataset_key": "swfsc_cufes", "life_stage": "egg", "n": 49572, "n_10m2": 0, "n_1000m3": 0},
    ]
    assert default_stage(p) == "larva"                       # most rows WITH effort, not most rows
    assert default_denominator(p, "larva") == "per_10m2"     # tie -> areal
    assert default_denominator([{"dataset_key": "x", "life_stage": "larva", "n": 1, "n_10m2": 0, "n_1000m3": 1}], "larva") == "per_1000m3"
    assert default_denominator([{"dataset_key": "x", "life_stage": "egg", "n": 1, "n_10m2": 0, "n_1000m3": 0}], "egg") == "raw"
    z = [{"dataset_key": "z", "life_stage": None, "n": 5, "n_10m2": 5, "n_1000m3": 5}]
    assert default_stage(z) is None and default_denominator(z, None) == "per_10m2"
    assert default_stage([]) is None
