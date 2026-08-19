"""Release access: version resolution offline, live reads gated on network availability."""
import socket

import pytest

from calcofi4py import cc_catalog, cc_get_db, cc_resolve_version


def _online() -> bool:
    try:
        socket.create_connection(("storage.googleapis.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def test_resolve_rejects_garbage():
    with pytest.raises(ValueError):
        cc_resolve_version("2026.08.14")  # missing the v


needs_net = pytest.mark.skipif(not _online(), reason="no network to storage.googleapis.com")


@needs_net
def test_catalog_shape():
    cat = cc_catalog("latest")
    names = {t["name"] for t in cat["tables"]}
    assert {"sample", "obs", "dataset", "cruise"} <= names
    assert any(t.get("partitioned") for t in cat["tables"])
    assert any(t.get("supplemental") for t in cat["tables"])


@needs_net
def test_get_db_views_and_supplemental_gating():
    con = cc_get_db(tables=["cruise", "ship"])
    tbls = {r[0] for r in con.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    assert tbls == {"cruise", "ship"}
    n = con.sql("SELECT count(*) FROM cruise").fetchone()[0]
    assert n > 500

    con2 = cc_get_db()  # default: supplemental excluded
    tbls2 = {r[0] for r in con2.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    assert "obs" in tbls2 and "obs_ctd_full" not in tbls2
