import duckdb

from calcofi4py import QUAL_EXCLUDE, qual_ok_sql


def test_qual_ok_sql_keeps_unflagged_and_drops_bad_codes():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE obs AS SELECT * FROM (VALUES "
        "(1,'calcofi_bottle',NULL),(2,'calcofi_bottle','6.0'),(3,'calcofi_bottle','8.0'),"
        "(4,'calcofi_bottle','9'),(5,'calcofi_ctd-cast','2'),(6,'calcofi_ctd-cast','9'),"
        "(7,'calcofi_dic','2'),(8,'calcofi_dic','3'),(9,'swfsc_ichthyo','8')"
        ") t(id, dataset_key, measurement_qual)"
    )
    kept = [r[0] for r in con.execute(f"SELECT id FROM obs o WHERE {qual_ok_sql('o')} ORDER BY id").fetchall()]
    # bottle: NULL + 6 kept, 8.0 + 9 dropped; ctd: 2 kept, 9 dropped; dic: 2 kept,
    # 3 dropped; ichthyo has no vocabulary so its "8" is kept
    assert kept == [1, 2, 5, 7, 9]
    assert [r[0] for r in con.execute(f"SELECT id FROM obs WHERE {qual_ok_sql()} ORDER BY id").fetchall()] == kept
    assert set(QUAL_EXCLUDE) == {"calcofi_bottle", "calcofi_ctd-cast", "calcofi_dic"}
