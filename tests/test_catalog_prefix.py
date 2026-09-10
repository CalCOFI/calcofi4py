import os
import pytest
import calcofi4py as cc


def _online():
    try:
        cc.cc_list_versions()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _online(), reason="no network")
def test_pinned_version_falls_back_to_the_promoted_prefix(monkeypatch):
    monkeypatch.setenv("CALCOFI_RELEASE_PREFIX", "ducklake-nowhere/releases")
    monkeypatch.delenv("CALCOFI_RELEASE_VERSION", raising=False)
    assert cc.cc_catalog("v2026.09.06")["version"] == "v2026.09.06"


@pytest.mark.skipif(not _online(), reason="no network")
def test_latest_resolves_through_the_env_version(monkeypatch):
    monkeypatch.delenv("CALCOFI_RELEASE_PREFIX", raising=False)
    monkeypatch.setenv("CALCOFI_RELEASE_VERSION", "v2026.09.06")
    assert cc.cc_catalog("latest")["version"] == "v2026.09.06"
