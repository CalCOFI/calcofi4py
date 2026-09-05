"""cc_cite() — shared byte-for-byte with calcofi4r (calcofi4r/tests/testthat/fixtures/cite_*),
generated from this same synthetic three-dataset `dataset` table + catalog: calcofi_dic (DOI +
CC-BY-4.0), cce-lter_zoodb (custom license), farallon_bird-mammal (acknowledgement, no DOI). See
CalCOFI/workflows .claude/plans_todo/2026-09-03 WS-A2.
"""
import json
from pathlib import Path

import duckdb
import pytest

from calcofi4py import cc_cite

FX = Path(__file__).parent / "fixtures"


def _con():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE dataset AS SELECT * FROM (VALUES
          ('calcofi_dic', 'CalCOFI Dissolved Inorganic Carbon Data',
           'Wang, X.J. et al. (2021). CalCOFI Dissolved Inorganic Carbon Data. NOAA National Centers for Environmental Information.',
           'CC-BY-4.0', NULL, '10.25921/3w9f-jd72', NULL, 'Wang, X.J.; Sutula, M.'),
          ('cce-lter_zoodb', 'Zooplankton biomass and net sampling data (CCE LTER ZooDB)',
           'CCE LTER (2019). Zooplankton biomass and net sampling data. oceaninformatics.ucsd.edu.',
           'custom', 'https://oceaninformatics.ucsd.edu/zoodb/terms', NULL, NULL, 'CCE LTER'),
          ('farallon_bird-mammal', 'Farallon Islands seabird and pinniped census',
           'Point Blue Conservation Science (2020). Farallon Islands seabird and pinniped census.',
           'CC-BY-4.0', NULL, NULL,
           'Data collected under National Marine Sanctuary permit; please acknowledge Point Blue Conservation Science.',
           'Point Blue Conservation Science')
        ) t(dataset_key, dataset_name, citation_main, license, license_url, doi, acknowledgement, pi_names)
    """)
    return con


def _catalog():
    return {
        "version": "v2026.09.03",
        "release_date": "2026-09-03",
        "doi": "10.5281/zenodo.99999999",
        "citation": (
            "CalCOFI (2026). CalCOFI Integrated Database, release v2026.09.03 [Data set]. "
            "Scripps Institution of Oceanography, NOAA Fisheries, and California Department of "
            "Fish and Wildlife. https://doi.org/10.5281/zenodo.99999999"
        ),
    }


def _legacy_catalog():
    return json.loads((FX / "catalog_legacy.json").read_text())


def test_cite_all_matches_shared_fixtures(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())

    txt = cc_cite(con=con, version="v2026.09.03", format="text")
    fx_txt = (FX / "cite_text.txt").read_text()
    assert list(txt) == fx_txt.rstrip("\n").split("\n\n")
    assert txt.source == "release"

    bib = cc_cite(con=con, version="v2026.09.03", format="bibtex")
    fx_bib = (FX / "cite_bibtex.txt").read_text()
    assert str(bib) == fx_bib.rstrip("\n")
    assert bib.source == "release"

    csl = cc_cite(con=con, version="v2026.09.03", format="csl")
    fx_csl = json.loads((FX / "cite_csl.json").read_text())
    assert list(csl) == fx_csl
    assert csl.source == "release"


def test_default_order_is_alphabetical_dataset_key(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())
    out = cc_cite(con=con, version="v2026.09.03")
    assert len(out) == 4
    assert out[1].startswith("Wang, X.J.")
    assert out[2].startswith("CCE LTER")
    assert out[3].startswith("Point Blue")


def test_string_or_list_cites_just_those_keys_in_order(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())

    out = cc_cite("calcofi_dic", con=con, version="v2026.09.03")
    assert len(out) == 2 and out[1].startswith("Wang, X.J.")

    out2 = cc_cite(["farallon_bird-mammal", "calcofi_dic"], con=con, version="v2026.09.03")
    assert len(out2) == 3
    assert out2[1].startswith("Point Blue")
    assert out2[2].startswith("Wang, X.J.")


def test_dataframe_uses_distinct_dataset_key_first_occurrence_order(monkeypatch):
    pd = pytest.importorskip("pandas")
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())
    df = pd.DataFrame({"dataset_key": ["cce-lter_zoodb", "cce-lter_zoodb", "calcofi_dic"]})
    out = cc_cite(df, con=con, version="v2026.09.03")
    assert len(out) == 3  # release + 2 distinct keys, not 3 rows + release
    assert out[1].startswith("CCE LTER")
    assert out[2].startswith("Wang, X.J.")

    with pytest.raises(KeyError):
        cc_cite(pd.DataFrame({"x": [1]}), con=con, version="v2026.09.03")


def test_unknown_dataset_key_raises_naming_it(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())
    with pytest.raises(KeyError, match="nope_dataset"):
        cc_cite("nope_dataset", con=con, version="v2026.09.03")
    with pytest.raises(KeyError, match="nope"):
        cc_cite(["calcofi_dic", "nope"], con=con, version="v2026.09.03")


def test_invalid_format_raises():
    con = _con()
    with pytest.raises(ValueError):
        cc_cite(con=con, version="v2026.09.03", format="yaml")


def test_pre_a0_catalog_falls_back_to_computed_release_wording(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _legacy_catalog())
    out = cc_cite([], con=con, version="v2026.08.14", format="text")
    assert out.source == "computed"
    assert out[0] == (
        "CalCOFI (2026). CalCOFI Integrated Database, release v2026.08.14 [Data set]. "
        "Scripps Institution of Oceanography, NOAA Fisheries, and California Department of "
        "Fish and Wildlife. https://calcofi.io/db-schema/?v=v2026.08.14"
        "\nPage: https://calcofi.io/datasets/release/"
    )
    assert len(out) == 1


def test_bibtex_resolve_true_tries_doi_first_then_falls_back(monkeypatch):
    con = _con()
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())

    monkeypatch.setattr("calcofi4py.cite._doi_bibtex", lambda doi: f"@misc{{resolved_{doi}}}")
    out = cc_cite("calcofi_dic", con=con, version="v2026.09.03", format="bibtex", resolve=True)
    assert "@misc{resolved_10.25921/3w9f-jd72}" in out

    def _boom(doi):
        raise RuntimeError("offline")
    monkeypatch.setattr("calcofi4py.cite._doi_bibtex", _boom)
    out2 = cc_cite("calcofi_dic", con=con, version="v2026.09.03", format="bibtex", resolve=True)
    assert "@misc{calcofi_dic," in out2

    def _must_not_be_called(doi):
        raise AssertionError("must not be called when resolve=False")
    monkeypatch.setattr("calcofi4py.cite._doi_bibtex", _must_not_be_called)
    cc_cite("calcofi_dic", con=con, version="v2026.09.03", format="bibtex")  # resolve=False default


# the 18 columns the released `dataset` table had before the attribution contract
# (v2026.08.25, calcofi4db < 3.30.0): no doi, license_url or acknowledgement
_LEGACY_COLS = [
    "dataset_key", "provider", "dataset", "dataset_name", "dataset_name_short", "category",
    "color", "description", "citation_main", "citation_others", "link_calcofi_org",
    "link_data_source", "link_others", "tables", "coverage_temporal", "coverage_spatial",
    "license", "pi_names"]


def _legacy_con():
    con = duckdb.connect()
    con.execute("CREATE TABLE dataset (" + ", ".join(f"{c} VARCHAR" for c in _LEGACY_COLS) + ")")
    con.execute("""
        INSERT INTO dataset (dataset_key, provider, dataset, dataset_name, citation_main, license, pi_names) VALUES
          ('calcofi_dic', 'calcofi', 'dic', 'CalCOFI Dissolved Inorganic Carbon Data',
           'Wang, X.J. et al. (2021). CalCOFI Dissolved Inorganic Carbon Data. NOAA National Centers for Environmental Information.',
           'CC-BY-4.0', 'Wang, X.J.; Sutula, M.'),
          ('cce-lter_zoodb', 'cce-lter', 'zoodb', 'Zooplankton biomass and net sampling data (CCE LTER ZooDB)',
           'CCE LTER (2019). Zooplankton biomass and net sampling data. oceaninformatics.ucsd.edu.',
           'custom', 'CCE LTER'),
          ('farallon_bird-mammal', 'farallon', 'bird-mammal', 'Farallon Islands seabird and pinniped census',
           'Point Blue Conservation Science (2020). Farallon Islands seabird and pinniped census.',
           'CC-BY-4.0', 'Point Blue Conservation Science')
    """)
    return con


def test_pre_contract_dataset_table_cites_without_doi_license_url_acknowledgement(monkeypatch):
    con = _legacy_con()
    cols = [r[0] for r in con.execute("DESCRIBE dataset").fetchall()]
    assert len(cols) == 18
    assert not {"doi", "license_url", "acknowledgement"} & set(cols)
    monkeypatch.setattr("calcofi4py.cite.cc_catalog", lambda *a, **k: _catalog())

    # text: the release citation, then citation_main + its License line — and nothing the
    # table cannot supply (no DOI: / Acknowledgement: line, no URL after `custom`)
    txt = cc_cite(con=con, version="v2026.09.03")
    assert len(txt) == 4
    assert txt[0] == _catalog()["citation"] + "\nPage: https://calcofi.io/datasets/release/"
    assert txt.source == "release"
    assert txt[1] == ("Wang, X.J. et al. (2021). CalCOFI Dissolved Inorganic Carbon Data. "
                      "NOAA National Centers for Environmental Information.\nLicense: CC-BY-4.0"
                      "\nPage: https://calcofi.io/datasets/calcofi_dic/")
    assert txt[2] == ("CCE LTER (2019). Zooplankton biomass and net sampling data. "
                      "oceaninformatics.ucsd.edu.\nLicense: custom"
                      "\nPage: https://calcofi.io/datasets/cce-lter_zoodb/")
    assert not any(("DOI: " in t) or ("Acknowledgement: " in t) or ("License: custom (" in t) for t in txt)

    # bibtex: the dataset entries carry no doi / url field (the release entry keeps its DOI)
    bib = cc_cite(con=con, version="v2026.09.03", format="bibtex")
    ents = str(bib).split("\n\n")
    assert len(ents) == 4
    assert ents[1].startswith("@misc{calcofi_dic,")
    assert all("\n  doi " not in e and "\n  url " not in e for e in ents[1:])
    assert all("\n  note " in e for e in ents[1:])

    # csl: no DOI / URL on a dataset item; the note is the license alone
    csl = cc_cite(con=con, version="v2026.09.03", format="csl")
    assert len(csl) == 4
    assert "DOI" not in csl[1] and "URL" not in csl[1]
    assert csl[1]["note"] == "License: CC-BY-4.0"
    assert csl[2]["note"] == "License: custom"

    # a subset and a list of dicts go through the same path
    assert len(cc_cite("cce-lter_zoodb", con=con, version="v2026.09.03")) == 2
    assert len(cc_cite([{"dataset_key": "calcofi_dic"}, {"dataset_key": "calcofi_dic"}],
                       con=con, version="v2026.09.03")) == 2
