"""cc_cite() — the attribution contract's read side (plan 2026-09-03, WS-A2).

Every CalCOFI release cites itself and every dataset in it carries a checked
``citation_main``, a registered ``license`` and, where the source gives one, a
``doi`` and ``acknowledgement`` (``calcofi4db::check_dataset_citation()`` /
``release_citation()``, calcofi4db R/citation.R, calcofi4db >= 3.30.0). ``cc_cite()``
reads the ``dataset`` table of a connection and a release's ``catalog.json`` and
formats them the way someone putting CalCOFI data in a paper needs them.

Mirrors ``calcofi4r::cc_cite()`` (calcofi4r/R/cite.R) byte-for-byte — keep the two
implementations in step. Shared fixtures: ``tests/fixtures/cite_text.txt`` /
``cite_bibtex.txt`` / ``cite_csl.json``, byte-identical with
``calcofi4r/tests/testthat/fixtures/cite_*``.
"""

from __future__ import annotations

import re
import urllib.request

import duckdb

from .release import cc_catalog, cc_get_db, cc_resolve_version

# The release-citation wording, mirrored from calcofi4db::release_citation()
# (R/citation.R there). calcofi4r/calcofi4py do not depend on calcofi4db, so the
# formula is duplicated here and in calcofi4r/R/cite.R on purpose — the same
# precedent as density_sql(). Keep all three in step when it changes.
_PUBLISHER = (
    "Scripps Institution of Oceanography, NOAA Fisheries, and "
    "California Department of Fish and Wildlife"
)
_DB_SCHEMA_URL = "https://calcofi.io/db-schema/"

_YEAR_RE = re.compile(r"(18|19|20)[0-9]{2}")


def _s0(x) -> str:
    """None/NaN/empty -> ''; else the value as a trimmed string."""
    if x is None:
        return ""
    s = str(x)
    return "" if s.lower() == "nan" else s


def _release_computed(version: str, release_date: str | None = None, doi: str | None = None) -> str:
    """Computed exactly like calcofi4db::release_citation(version, date, doi); used only when the
    catalog predates the attribution contract (2026-09-03) and carries no ``citation`` of its own."""
    rd = _s0(release_date)
    year = rd[:4] if rd else version[1:5]
    doi = _s0(doi)
    locator = f"https://doi.org/{doi}" if doi else f"{_DB_SCHEMA_URL}?v={version}"
    return f"CalCOFI ({year}). CalCOFI Integrated Database, release {version} [Data set]. {_PUBLISHER}. {locator}"


def _release_fields(catalog: dict) -> dict:
    """The release entry's fields (id, citation text, title, author, year, publisher, doi, url), plus
    ``source`` ("release" when catalog["citation"] was used as is, "computed" when it had to be
    derived — mirrors calcofi4r::cc_climatology()'s ``source`` attribute)."""
    version = _s0(catalog.get("version"))
    has_cit = bool(_s0(catalog.get("citation")))
    doi = _s0(catalog.get("doi"))
    rd = _s0(catalog.get("release_date"))
    year = rd[:4] if rd else version[1:5]
    locator = f"https://doi.org/{doi}" if doi else f"{_DB_SCHEMA_URL}?v={version}"
    citation = catalog["citation"] if has_cit else _release_computed(version, catalog.get("release_date"), doi)
    return {
        "id": "calcofi_release_" + re.sub(r"[^A-Za-z0-9]+", "_", version),
        "citation": citation,
        "title": f"CalCOFI Integrated Database, release {version}",
        "author": "CalCOFI",
        "year": year,
        "publisher": _PUBLISHER,
        "doi": doi or None,
        "url": locator,
        "source": "release" if has_cit else "computed",
    }


# the ``dataset`` columns cc_cite() reads; any one absent from a release is None
_DATASET_COLS = ["dataset_key", "dataset_name", "citation_main", "license", "license_url",
                 "doi", "acknowledgement", "pi_names"]


def _rows(con: duckdb.DuckDBPyConnection, x) -> list[dict]:
    """Resolve which dataset_key values to cite, in the order to cite them: ``None`` -> every
    dataset in ``con``'s ``dataset`` table, alphabetical dataset_key order; a list of dataset_key
    strings, or anything carrying a ``dataset_key`` column (a pandas/polars DataFrame, a list of
    dicts) -> those keys, de-duplicated, in first-occurrence order. An unmatched key is a
    ``KeyError`` naming it — cc_cite() never silently drops one."""
    # select only the columns this release's ``dataset`` table has: a release frozen before
    # the attribution contract (calcofi4db < 3.30.0, e.g. v2026.08.25) carries no
    # license_url / doi / acknowledgement, and a fixed SELECT was a binder error on every
    # call instead of a citation with fewer lines
    have = [r[0] for r in con.execute("DESCRIBE dataset").fetchall()]
    present = [c for c in _DATASET_COLS if c in have]
    if "dataset_key" not in present:
        raise KeyError("cc_cite(): the `dataset` table has no dataset_key column")
    all_rows = con.execute(f"SELECT {', '.join(present)} FROM dataset").fetchall()
    by_key = {}
    for r in all_rows:
        d = dict(zip(present, r))
        for c in _DATASET_COLS:
            d.setdefault(c, None)
        by_key[d["dataset_key"]] = d

    if x is None:
        keys = sorted(by_key)
    elif hasattr(x, "__getitem__") and hasattr(x, "columns"):  # a pandas/polars DataFrame
        keys = list(dict.fromkeys(x["dataset_key"].to_list() if hasattr(x["dataset_key"], "to_list")
                                   else list(x["dataset_key"])))
    elif isinstance(x, str):
        keys = [x]
    else:
        seen = []
        for v in x:
            k = v["dataset_key"] if isinstance(v, dict) else v
            if k not in seen:
                seen.append(k)
        keys = seen

    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise KeyError(f"cc_cite(): unknown dataset_key(s): {', '.join(unknown)}")
    return [by_key[k] for k in keys]


def _license_line(row: dict) -> str | None:
    lic = _s0(row.get("license"))
    if not lic:
        return None
    if lic == "custom" and _s0(row.get("license_url")):
        return f"License: {lic} ({row['license_url']})"
    return f"License: {lic}"


def _doi_line(row: dict) -> str | None:
    doi = _s0(row.get("doi"))
    return f"DOI: https://doi.org/{doi}" if doi else None


def _ack_line(row: dict) -> str | None:
    ack = _s0(row.get("acknowledgement"))
    return f"Acknowledgement: {ack}" if ack else None


def _note(row: dict) -> str:
    """License + acknowledgement collapsed to one line (bibtex/CSL ``note``)."""
    return "; ".join(p for p in (_license_line(row), _ack_line(row)) if p)


def _year(citation_main: str) -> str | None:
    m = _YEAR_RE.search(citation_main or "")
    return m.group(0) if m else None


def _text_one(row: dict) -> str:
    cit = _s0(row.get("citation_main"))
    first = cit if cit else f"{row.get('dataset_name') or row['dataset_key']} [dataset]."
    lines = [first, _license_line(row), _doi_line(row), _ack_line(row)]
    return "\n".join(line for line in lines if line)


def _bibtex_entry(key: str, fields: dict) -> str:
    """One @misc entry, its fields padded so every ``=`` in the entry lines up (repo style);
    empty/None fields are dropped, never emitted blank."""
    fields = {k: v for k, v in fields.items() if v}
    w = max(len(k) for k in fields)
    body = ",\n".join(f"  {k:<{w}} = {{{v}}}" for k, v in fields.items())
    return f"@misc{{{key},\n{body}\n}}"


def _bibtex_release(rel: dict) -> str:
    return _bibtex_entry(rel["id"], {
        "title": rel["title"], "author": rel["author"], "year": rel["year"],
        "publisher": rel["publisher"], "doi": rel["doi"], "url": rel["url"]})


def _bibtex_one(row: dict) -> str:
    cit = _s0(row.get("citation_main"))
    ttl = row.get("dataset_name") or row["dataset_key"]
    doi = _s0(row.get("doi"))
    note = _note(row)
    return _bibtex_entry(row["dataset_key"], {
        "title": ttl, "howpublished": cit, "year": _year(cit),
        "doi": doi or None,
        "url": f"https://doi.org/{doi}" if doi else None,
        "note": note or None})


def _csl_author(pi_names, fallback: str = "CalCOFI") -> list[dict]:
    nm = _s0(pi_names)
    people = [p.strip() for p in nm.split(";")] if nm else [fallback]
    return [{"literal": p} for p in people]


def _csl_release(rel: dict) -> dict:
    item = {
        "id": rel["id"], "type": "dataset", "title": rel["title"],
        "author": [{"literal": rel["author"]}],
        "issued": {"date-parts": [[int(rel["year"])]]},
        "publisher": rel["publisher"]}
    if rel["doi"]:
        item["DOI"] = rel["doi"]
    item["URL"] = rel["url"]
    return item


def _csl_one(row: dict) -> dict:
    cit = _s0(row.get("citation_main"))
    yr = _year(cit)
    ttl = row.get("dataset_name") or row["dataset_key"]
    doi = _s0(row.get("doi"))
    note = _note(row)
    item = {"id": row["dataset_key"], "type": "dataset", "title": ttl,
            "author": _csl_author(row.get("pi_names"))}
    if yr:
        item["issued"] = {"date-parts": [[int(yr)]]}
    if doi:
        item["DOI"] = doi
        item["URL"] = f"https://doi.org/{doi}"
    if note:
        item["note"] = note
    return item


def _doi_bibtex(doi: str) -> str | None:
    """``resolve=True`` only: doi.org content negotiation. Never called by default — cc_cite()'s
    default path is offline."""
    req = urllib.request.Request(
        f"https://doi.org/{doi}", headers={"Accept": "application/x-bibtex"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (fixed doi.org host)
        if r.status != 200:
            return None
        return r.read().decode("utf-8").strip()


class Cite(str):
    """A ``str`` (the bibtex string, or one text entry) carrying a ``source`` attribute — mirrors the
    R side's ``attr(x, "source")``. Behaves exactly like ``str`` everywhere; only ``.source`` is extra."""

    source: str

    def __new__(cls, value: str, source: str):
        obj = super().__new__(cls, value)
        obj.source = source
        return obj


class CiteList(list):
    """A ``list`` (of text entries, or of CSL items) carrying a ``source`` attribute."""

    source: str


def cc_cite(
    x=None,
    version: str = "latest",
    format: str = "text",  # noqa: A002 (mirrors calcofi4r::cc_cite()'s `format`)
    con: duckdb.DuckDBPyConnection | None = None,
    resolve: bool = False,
):
    """Cite CalCOFI data.

    Every CalCOFI release cites itself (``catalog.json``'s ``citation``, set by
    ``calcofi4db::add_release_citation()``) and every dataset in it carries a checked
    ``citation_main``, a registered ``license`` and, where the source gives one, a ``doi`` and
    ``acknowledgement`` (``calcofi4db::check_dataset_citation()``, calcofi4db >= 3.30.0, the
    attribution contract). ``cc_cite()`` is the one place that formats them for a paper, a data
    management plan or a ``.bib`` file — read the ``dataset`` table off ``con``, do not build a
    citation string by hand.

    Every call returns the **release citation first**, then one entry per dataset. With ``x =
    None`` (default) that is every dataset in the release, alphabetical by ``dataset_key``; a list
    of ``dataset_key`` strings, a single ``dataset_key`` string, or anything carrying a
    ``dataset_key`` column (a pandas/polars DataFrame — so ``cc_cite(cc_read_obs(...).df())``
    works directly on a query result) cites just those, de-duplicated, in the order given. A
    ``dataset_key`` that does not exist in the release raises ``KeyError`` naming it.

    Each dataset entry always carries its ``citation_main``; ``format="text"`` appends a
    ``License: <id>`` line (plus the URL, for a ``custom`` license), a ``DOI:`` line when the
    dataset has one, and an ``Acknowledgement:`` line when the source requires one.
    ``format="bibtex"`` and ``format="csl"`` fold license and acknowledgement into one
    ``note``/``note`` field instead, since neither format has a natural place for more than one.

    ``format="bibtex"`` builds every ``@misc{...}`` entry **offline**, from the fields already on
    ``dataset`` and in the catalog — nothing here calls the network by default. ``resolve=True``
    instead fetches ``https://doi.org/<doi>`` with ``Accept: application/x-bibtex`` for any entry
    that has a DOI (falling back to the offline entry for one that does not, or if the fetch
    fails).

    A release frozen before the attribution contract (2026-09-03) carries no ``citation`` in its
    catalog; ``cc_cite()`` computes the same wording ``calcofi4db::release_citation()`` would have
    written (``.source`` attribute ``"computed"`` on the result, mirroring
    ``calcofi4r::cc_climatology()``'s ``source``), rather than erroring or citing nothing.

    The **software** itself is cited separately — ``citation("calcofi4r")`` for R,
    ``calcofi4py.__citation__`` for Python; ``cc_cite()`` is for the *data*.

    Parameters
    ----------
    x : None, str, list, or a DataFrame-like carrying a ``dataset_key`` column
    version : release version (default ``"latest"``). Only consulted for the release-level
        citation (``cc_catalog(version)``) — with ``con`` supplied, pass the version ``con`` was
        opened on if it is not ``"latest"``.
    format : ``"text"`` (a list of str, release citation first), ``"bibtex"`` (one str, every
        ``@misc{...}`` entry concatenated) or ``"csl"`` (a list of CSL-JSON dicts, one per entry).
    con : optional open connection from :func:`cc_get_db`; when given it is used as is.
    resolve : ``format="bibtex"`` only — fetch the DOI's own BibTeX from doi.org for any entry
        with a DOI, instead of building it offline (default ``False``).

    Returns
    -------
    See ``format``. The result carries a ``.source`` attribute (``"release"`` or ``"computed"``)
    describing where the release-level citation came from.

    >>> cc_cite("calcofi_dic")
    >>> cc_cite(format="bibtex")
    >>> cc_cite(df)  # df carries a dataset_key column
    """
    if format not in ("text", "bibtex", "csl"):
        raise ValueError(f"format must be 'text', 'bibtex' or 'csl', got {format!r}")

    if con is None:
        version = cc_resolve_version(version)
        con = cc_get_db(version)
    catalog = cc_catalog(version)
    rel = _release_fields(catalog)
    rows = _rows(con, x)

    if format == "text":
        out = CiteList([rel["citation"]] + [_text_one(r) for r in rows])
        out.source = rel["source"]
        return out

    if format == "bibtex":
        entries = [_bibtex_release(rel)]
        for row in rows:
            doi = _s0(row.get("doi"))
            got = None
            if resolve and doi:
                try:
                    got = _doi_bibtex(doi)
                except Exception:  # noqa: BLE001 — offline/DNS/HTTP: fall back, never raise
                    got = None
            entries.append(got if got else _bibtex_one(row))
        return Cite("\n\n".join(entries), rel["source"])

    # csl
    out = CiteList([_csl_release(rel)] + [_csl_one(r) for r in rows])
    out.source = rel["source"]
    return out
