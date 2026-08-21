"""Live PostgreSQL tests — need a tunnel + ~/.pgpass; gated on CALCOFI_PG_TEST=1."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("CALCOFI_PG_TEST"),
    reason="set CALCOFI_PG_TEST=1 with a tunnel + ~/.pgpass to run",
)


def test_pg_connect_reaches_calcofi():
    from calcofi4py import cc_pg_connect

    with cc_pg_connect(tunnel=True) as con:          # opens (or reuses) the SSH tunnel itself
        schemas = {r[0] for r in con.execute("SELECT nspname FROM pg_namespace").fetchall()}
        assert {"ctd", "work"} <= schemas


def test_pg_attach_joins_release_and_pg():
    from calcofi4py import cc_get_db, cc_pg_attach, cc_pg_tunnel

    cc_pg_tunnel(local_port=int(os.environ.get("PGPORT", 5432)))   # DuckDB's libpq needs the tunnel up too
    con = cc_get_db(tables=["cruise"])
    cc_pg_attach(con)
    n = con.sql("SELECT count(*) FROM pg.ctd.file").fetchone()[0]
    assert n > 0


def test_propose_then_withdraw_round_trip_leaves_no_residue():
    import calcofi4py as cc
    con = cc.cc_pg_connect(tunnel=True)
    try:
        (scan_id,) = con.execute(
            "SELECT scan_id FROM ctd.v_scan_best WHERE study='2304SH' AND cast_id='2304_001d' AND depth=20"
        ).fetchone()
        n = cc.cc_propose_flags(con, [scan_id], "temp1", 3, "pytest round trip", commit=False)
        assert n == 1
        (flag_id, status) = con.execute(
            "SELECT flag_id, status FROM ctd.flag WHERE scan_id=%s AND variable='temp1' "
            "AND created_by=current_user ORDER BY flag_id DESC LIMIT 1", (scan_id,)).fetchone()
        assert status == "proposed"
        assert cc.cc_withdraw_flags(con, [flag_id], note="pytest", commit=False) == 1
        (status, note) = con.execute(
            "SELECT status, review_note FROM ctd.flag WHERE flag_id=%s", (flag_id,)).fetchone()
        assert (status, note) == ("withdrawn", "pytest")
        assert cc.cc_withdraw_flags(con, [flag_id], commit=False) == 0   # already withdrawn: not counted
    finally:
        con.rollback()   # nothing reaches the ledger
        con.close()
