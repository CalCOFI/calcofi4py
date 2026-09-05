"""cc_datasets() / cc_dataset_page_url() — the dataset-catalog record's read side (plan
2026-09-05, WS-P2). Fixture shared byte-for-byte with calcofi4r
(calcofi4r/tests/testthat/fixtures/datasets_sample.json).
"""
from pathlib import Path

import pytest

from calcofi4py import cc_dataset_page_url, cc_datasets
from calcofi4py.catalog import _datasets_read

FX = Path(__file__).parent / "fixtures" / "datasets_sample.json"


def test_page_url_built_from_the_key_never_a_lookup_table():
    assert cc_dataset_page_url("calcofi_bottle") == "https://calcofi.io/datasets/calcofi_bottle/"
    assert cc_dataset_page_url("cce-lter_zoodb") == "https://calcofi.io/datasets/cce-lter_zoodb/"


def test_datasets_read_one_row_per_dataset_with_list_fields():
    ds = _datasets_read(str(FX), what="datasets")
    assert len(ds) == 2
    assert [d["dataset_key"] for d in ds] == ["calcofi_dic", "cce-lter_zoodb"]
    assert isinstance(ds[0]["distributions"], list)
    assert isinstance(ds[0]["registrations"], list)
    for d in ds:
        assert d["links"]["page"] == cc_dataset_page_url(d["dataset_key"])

    holdings = _datasets_read(str(FX), what="holdings")
    assert len(holdings) == 1
    assert holdings[0]["key"] == "calcofi_prodo"

    ref = _datasets_read(str(FX), what="reference")
    assert ref == []


def test_datasets_read_rejects_bad_what():
    with pytest.raises(ValueError):
        _datasets_read(str(FX), what="nope")


def test_cc_datasets_builds_the_url_from_version_and_base_https(monkeypatch):
    calls = {}

    def fake_read(url, what="datasets", version_hint=None):
        calls["url"] = url
        calls["what"] = what
        return [{"ok": True}]

    monkeypatch.setattr("calcofi4py.catalog.cc_resolve_version", lambda v="latest": "v2026.09.05")
    monkeypatch.setattr("calcofi4py.catalog._datasets_read", fake_read)
    out = cc_datasets(version="latest", what="holdings", base_https="https://example.org")
    assert calls["url"] == "https://example.org/ducklake/releases/v2026.09.05/datasets.json"
    assert calls["what"] == "holdings"
    assert out == [{"ok": True}]


def test_datasets_read_raises_naming_the_version_when_missing():
    with pytest.raises(LookupError, match="v2026.01.01"):
        _datasets_read("https://storage.googleapis.com/calcofi-db-does-not-exist/x.json",
                       what="datasets", version_hint="v2026.01.01")
