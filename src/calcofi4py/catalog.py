"""cc_datasets() — the dataset-catalog record's read side (plan 2026-09-05, WS-P2).

Every release writes a ``datasets.json`` (``calcofi4db::build_dataset_catalog()``, calcofi4db >=
4.1.0): one record per integrated dataset, plus ``holdings`` (not yet in the database) and
``reference`` (cruises, stations, spatial layers). ``cc_datasets()`` is the one place that reads it
into a table — a page's Access table, a query's Datasets category, a consumer's "dataset page ↗"
link all resolve the same way: ``https://calcofi.io/datasets/{dataset_key}/``, built from the key,
never a hard-coded list.

Mirrors ``calcofi4r::cc_datasets()`` / ``cc_dataset_page_url()`` (calcofi4r R/catalog.R)
byte-for-byte over the shared fixture ``tests/fixtures/datasets_sample.json`` (==
``calcofi4r/tests/testthat/fixtures/datasets_sample.json``) — keep the two in step.
"""

from __future__ import annotations

import json
import urllib.request

from .release import BUCKET_HTTPS, cc_resolve_version


def cc_dataset_page_url(dataset_key: str) -> str:
    """The ``https://calcofi.io/datasets/{dataset_key}/`` page URL for a dataset.

    The one place a URL is built from a ``dataset_key`` — every consumer that names a dataset
    should call this (or its R equivalent) rather than hard-code the pattern.
    """
    return f"https://calcofi.io/datasets/{dataset_key}/"


def _read_json(url: str) -> dict:
    if url.startswith("http://") or url.startswith("https://"):
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (fixed public host)
            return json.loads(r.read().decode())
    # a local path (fixtures, tests)
    with open(url, encoding="utf-8") as f:
        return json.load(f)


def _datasets_read(url: str, what: str = "datasets", version_hint: str | None = None) -> list[dict]:
    """Read one table (``datasets`` | ``holdings`` | ``reference``) of a ``datasets.json`` record
    from any location ``_read_json`` can open (an https URL or a local path — tests use a fixture
    file directly, so the record-reading logic and the URL-building logic are tested apart)."""
    if what not in ("datasets", "holdings", "reference"):
        raise ValueError(f"what must be 'datasets', 'holdings' or 'reference', got {what!r}")
    try:
        rec = _read_json(url)
    except Exception as e:  # noqa: BLE001 — re-raise with the version named
        raise LookupError(
            f"cc_datasets(): could not read datasets.json for {version_hint or url} ({url}). "
            "Releases before calcofi4db 4.1.0 (2026-09) carry no dataset catalog."
        ) from e
    return rec.get(what) or []


def cc_datasets(
    version: str = "latest",
    what: str = "datasets",
    base_https: str = BUCKET_HTTPS,
) -> list[dict]:
    """List CalCOFI datasets (the dataset-catalog record).

    Reads a release's ``datasets.json`` — the record every dataset page, ERDDAP ``infoUrl``, and
    ``cc_cite()``'s page line are built from (``calcofi4db::build_dataset_catalog()``, calcofi4db
    >= 4.1.0) — into a list of dicts, one per record. A release frozen before the dataset catalog
    (calcofi4db < 4.1.0, before 2026-09) carries no ``datasets.json``; this raises ``LookupError``
    naming the version rather than returning an empty list, so a caller does not mistake "no
    catalog yet" for "no datasets".

    Parameters
    ----------
    version : release version (default ``"latest"``)
    what : which table of the record to return: ``"datasets"`` (default, the 16+ integrated
        datasets), ``"holdings"`` (datasets known but not yet in the database) or ``"reference"``
        (cruises, stations, spatial layers, bathymetry)
    base_https : https root of the bucket

    Returns
    -------
    list[dict], one per record. ``pandas.DataFrame(cc_datasets())`` makes a table of it; a
    dataset's own page is ``row["links"]["page"]`` (or ``cc_dataset_page_url(row["dataset_key"])``).

    >>> ds = cc_datasets()
    >>> [d["dataset_key"] for d in ds]
    >>> cc_datasets(what="holdings")
    """
    version = cc_resolve_version(version)
    url = f"{base_https}/ducklake/releases/{version}/datasets.json"
    return _datasets_read(url, what=what, version_hint=version)
