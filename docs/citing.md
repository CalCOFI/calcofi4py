# Citing CalCOFI data

CalCOFI's integrated database is not one thing to cite — it is a **release** (a
specific, versioned snapshot) built from **datasets**, each contributed by its
own program under its own license, and often its own DOI. Citing "CalCOFI" and
citing the CTD-bottle time series and citing the Farallon seabird census are
three different citations, and a paper that used all three owes all three.

Every field involved — `citation_main`, `license`, `doi`, `acknowledgement` —
is checked at release time (`calcofi4db.check_dataset_citation()`, the
attribution contract): a citation with a year and a locator, a license
registered in `metadata/license.csv`, a DOI that actually resolves.
[`cc_cite()`][calcofi4py.cite.cc_cite] is the one place that reads those
fields back out and formats them, so you never have to build a citation
string by hand or guess whether a `license_url` is required.

```python
import calcofi4py as cc

REL = cc.cc_resolve_version("latest")
cc.cc_cite(version=REL)
# ['CalCOFI (2026). CalCOFI Integrated Database, release v2026.09.03 [Data set]. Scripps
#  Institution of Oceanography, NOAA Fisheries, and California Department of Fish and
#  Wildlife. https://doi.org/10.5281/zenodo.22281994',
#  'Wang, X.J. et al. (2021). CalCOFI Dissolved Inorganic Carbon Data. ...\nLicense: CC-BY-4.0\n...',
#  ...]
```

The **first** entry is always the release itself, cited under the concept DOI
once Zenodo has minted one for the tag, or a stable `db-schema` URL until
then. Every entry after it is one dataset, in alphabetical `dataset_key`
order by default.

## Citing just what you used

Pass the `dataset_key`(s) you actually queried — never everything, and never
whichever ones you remember typing:

```python
cc.cc_cite(["calcofi_bottle", "calcofi_ctd-cast"], version=REL)
```

Better still, hand `cc_cite()` the **query result itself**. Anything carrying
a `dataset_key` column — a pandas or polars DataFrame, a list of dicts —
works directly: the distinct keys the query actually touched are what gets
cited, in the order they first appear.

```python
con = cc.cc_get_db(version=REL)
d = con.sql("""
  SELECT * FROM obs
  WHERE dataset_key IN ('calcofi_dic', 'calcofi_bottle')
    AND measurement_type = 'temperature'
  LIMIT 500
""").df()

cc.cc_cite(d, version=REL)
```

An unrecognized `dataset_key` raises `KeyError` naming it, rather than a
citation silently missing a dataset:

```python
cc.cc_cite("not_a_real_dataset", version=REL)
# KeyError: "cc_cite(): unknown dataset_key(s): not_a_real_dataset"
```

## Three formats

`format="text"` (the default, above) is meant for a methods section or an
email. `format="bibtex"` builds a `.bib`-ready entry per citation, and
`format="csl"` returns [CSL-JSON](https://citeproc-js.readthedocs.io/) items —
what Zotero, Pandoc citations and most reference managers import directly.

```python
print(cc.cc_cite("calcofi_dic", version=REL, format="bibtex"))
# @misc{calcofi_release_v2026_09_03,
#   title     = {CalCOFI Integrated Database, release v2026.09.03},
#   ...
# }
#
# @misc{calcofi_dic,
#   title        = {CalCOFI Dissolved Inorganic Carbon Data},
#   howpublished = {Wang, X.J. et al. (2021). ...},
#   ...
# }

cc.cc_cite("calcofi_dic", version=REL, format="csl")[1]
# {'id': 'calcofi_dic', 'type': 'dataset', 'title': 'CalCOFI Dissolved Inorganic Carbon Data',
#  'author': [{'literal': 'Wang, X.J.'}, {'literal': 'Sutula, M.'}],
#  'issued': {'date-parts': [[2021]]}, 'DOI': '10.25921/3w9f-jd72', ...}
```

`format="bibtex"` builds every entry **offline**, from the fields already on
the release's `dataset` table and in its `catalog.json` — nothing here calls
the network by default. `resolve=True` is the only network path: for any
entry with a DOI, it fetches the DOI's own BibTeX from `doi.org` instead
(falling back to the offline entry if that fetch fails), which some reference
managers format slightly differently.

```python
cc.cc_cite("calcofi_dic", version=REL, format="bibtex", resolve=True)
```

## Citing an older release

A release frozen before the attribution contract landed (2026-09-03) has no
`citation` in its `catalog.json`. `cc_cite()` computes the same wording
`calcofi4db.release_citation()` would have written rather than erroring, and
marks the result so you can tell which happened — `"release"` means the
catalog carried its own citation, `"computed"` means `cc_cite()` derived it:

```python
cc.cc_cite([], version=REL).source
# 'release'
```

## Citing the software, separately

`cc_cite()` is for the **data**. To cite the package itself — appropriate
alongside the data citation when `calcofi4py` did real analytical work, not
just I/O — use `calcofi4py.__citation__`:

```python
cc.__citation__
```

The R sibling, [`calcofi4r`](https://calcofi.io/calcofi4r), mirrors every
part of `cc_cite()` above byte-for-byte under the same name
(`calcofi4r::cc_cite()`) — the same release and dataset citations, read the
same way, for anyone working in R instead of a notebook.
