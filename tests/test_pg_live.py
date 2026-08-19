"""Live PostgreSQL tests — need a tunnel + ~/.pgpass; gated on CALCOFI_PG_TEST=1."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("CALCOFI_PG_TEST"),
    reason="set CALCOFI_PG_TEST=1 with a tunnel + ~/.pgpass to run",
)


def test_pg_connect_reaches_calcofi():
    from calcofi4py import cc_pg_connect

    with cc_pg_connect() as con:
        schemas = {r[0] for r in con.execute("SELECT nspname FROM pg_namespace").fetchall()}
        assert {"ctd", "work"} <= schemas


def test_pg_attach_joins_release_and_pg():
    from calcofi4py import cc_get_db, cc_pg_attach

    con = cc_get_db(tables=["cruise"])
    cc_pg_attach(con)
    n = con.sql("SELECT count(*) FROM pg.ctd.file").fetchone()[0]
    assert n > 0
