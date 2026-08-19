"""Pure-logic tests (no server, no network) — mirrors calcofi4r tests/testthat/test-postgres.R."""
import platform

import pytest

from calcofi4py import cc_on_server, cc_pgpass_user
from calcofi4py.postgres import _port_open


@pytest.fixture
def pgpass(tmp_path, monkeypatch):
    f = tmp_path / "pgpass"
    f.write_text(
        "# comment line\n"
        "\n"
        "otherhost:5432:*:someone:pw\n"
        "localhost:5432:*:rswalethorp:s3cret:with:colons\n"
        "postgis:5432:calcofi:bmgire:pw2\n"
        "*:*:*:fallback:pw3\n"
    )
    monkeypatch.setenv("PGPASSFILE", str(f))
    return f


def test_pgpass_user_matches_host_port_db(pgpass):
    assert cc_pgpass_user("localhost", 5432, "calcofi") == "rswalethorp"
    assert cc_pgpass_user("postgis", 5432, "calcofi") == "bmgire"


def test_pgpass_user_wildcard_fallbacks(pgpass):
    assert cc_pgpass_user("postgis", 5432, "gis") == "fallback"       # db mismatch
    assert cc_pgpass_user("localhost", 15432, "calcofi") == "fallback"  # port mismatch


def test_pgpass_user_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PGPASSFILE", str(tmp_path / "missing"))
    assert cc_pgpass_user("localhost", 5432, "calcofi") is None


def test_on_server_env_override(monkeypatch):
    monkeypatch.setenv("CALCOFI_ON_SERVER", "1")
    assert cc_on_server() is True
    monkeypatch.delenv("CALCOFI_ON_SERVER")
    if not (platform.system() == "Linux" and __import__("pathlib").Path("/share/github/CalCOFI").is_dir()):
        assert cc_on_server() is False


def test_port_open_false_on_closed_port():
    assert _port_open("127.0.0.1", 1) is False
