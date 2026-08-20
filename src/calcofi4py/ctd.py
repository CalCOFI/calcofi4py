"""CTD QA/QC helpers: read casts and scans, run portable QC rules, propose flags,
derive clean 1 m binned products.

Everything here targets the ``ctd`` schema of the team's PostgreSQL database
(server ``postgis/init/40_ctd.sql``): the **originals never change** — a problem
is a row proposed into ``ctd.flag``, a curator accepts or rejects it, and the
generated views ``ctd.v_scan_qc`` / ``ctd.v_scan_clean`` present originals and
accepted QC side by side. The QC checks are straight ports of the SQL rule
registry in ``CalCOFI/workflows`` ``metadata/qc_rules/`` (same thresholds, same
neighbour-agreement logic), re-targeted from the release tables onto
``ctd.v_scan_best``.

Reads return pandas DataFrames. Connections come from
:func:`calcofi4py.cc_pg_connect`.

>>> import calcofi4py as cc
>>> con = cc.cc_pg_connect(tunnel=True)
>>> casts = cc.cc_ctd_casts(con, "2607SH")
>>> spikes = cc.cc_qc_spike(con, "2607SH", "tempave")
>>> cc.cc_propose_flags(con, spikes.scan_id, "tempave", 4,
...     reason="single-scan spike, neighbours agree", rule_key="ctd_spike_v1")
"""

from __future__ import annotations

from typing import Iterable

try:
    import pandas as pd
except ImportError as e:  # pragma: no cover
    raise ImportError("calcofi4py.ctd needs pandas: pip install 'calcofi4py[viz]'") from e

__all__ = [
    "cc_ctd_casts",
    "cc_ctd_scans",
    "cc_qc_spike",
    "cc_qc_sensor_pair",
    "cc_qc_range",
    "cc_propose_flags",
    "cc_flags",
    "cc_bin_1m",
    "cc_station_map",
    "cc_profile_plot",
    "cc_section_plot",
]

_IDENT_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def _ident(name: str) -> str:
    """Validate a lowercase SQL identifier (column names are interpolated into SQL)."""
    if not name or not set(name) <= _IDENT_OK or name[0].isdigit():
        raise ValueError(f"not a valid column name: {name!r}")
    return name


def _read_sql(con, sql: str, params=None) -> "pd.DataFrame":
    cur = con.execute(sql, params)
    cols = [d.name for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


# ── read ──────────────────────────────────────────────────────────────────────

def cc_ctd_casts(con, study: str, best_only: bool = True) -> "pd.DataFrame":
    """One row per physical cast of a cruise, from ``ctd.cast``.

    :param con: psycopg connection (:func:`calcofi4py.cc_pg_connect`)
    :param study: source cruise id as in the files, e.g. ``"2607SH"``
    :param best_only: only the best data stage per cruise × direction (default);
        ``False`` includes superseded preliminary/duplicate archives
    :return: DataFrame with ``file_id, cast_id, cast_dir, sta_id, line, sta,
        datetime_utc, lat, lon, n_scans, depth_min, depth_max, cruise_key``
    """
    return _read_sql(con, """
        SELECT file_id, cast_id, cast_dir, ord_occ, sta_id, line, sta,
               datetime_utc, lat, lon, n_scans, depth_min, depth_max,
               cruise_key, data_stage, is_best_stage
        FROM ctd.cast WHERE study = %s AND (is_best_stage OR NOT %s)
        ORDER BY datetime_utc, cast_dir
        """, (study, best_only))


def cc_ctd_scans(
    con,
    study: str,
    columns: Iterable[str] = ("tempave", "salt1", "ox1"),
    cast_id: str | None = None,
    qc: bool = True,
) -> "pd.DataFrame":
    """Scan-level data for a cruise from ``ctd.v_scan_qc`` (best stage).

    :param columns: measurement columns to include (see ``ctd.scan_column``);
        with ``qc=True`` each also brings its ``<col>_qc`` (accepted IODE flag)
        and ``<col>_fix`` (accepted corrected value)
    :param cast_id: restrict to one cast (e.g. ``"2607_020d"``); default all
    :param qc: read from ``ctd.v_scan_qc`` (default) vs raw ``ctd.v_scan_best``
    :return: DataFrame keyed ``scan_id``, with ``cast_id, cast_dir, depth,
        date_time_utc, lat_dec, lon_dec`` + the requested columns
    """
    cols = [_ident(c) for c in columns]
    view = "ctd.v_scan_qc" if qc else "ctd.v_scan_best"
    extra = ", ".join(
        c if not qc else f"{c}, {c}_qc, {c}_fix" for c in cols)
    where, params = "s.study = %s", [study]
    if cast_id is not None:
        where += " AND s.cast_id = %s"
        params.append(cast_id)
    return _read_sql(con, f"""
        SELECT s.scan_id, s.cast_id, f.cast_dir, s.row_num, s.depth,
               s.date_time_utc, s.lat_dec, s.lon_dec, {extra}
        FROM {view} s JOIN ctd.file f USING (file_id)
        WHERE {where}
        ORDER BY s.cast_id, s.depth
        """, params)


# ── QC checks (ports of metadata/qc_rules/sql/*, re-targeted onto ctd.v_scan_best) ──

def cc_qc_spike(
    con,
    study: str,
    column: str = "tempave",
    spike_threshold: float = 0.5,
    neighbour_tol: float = 0.5,
) -> "pd.DataFrame":
    """Single-scan spikes against a locally smooth profile (``ctd_spike.sql``).

    Neighbour agreement is the whole trick: a point qualifies only if it deviates
    from the midpoint of its neighbours by more than ``spike_threshold`` WHILE
    the neighbours agree with each other within ``neighbour_tol`` — otherwise
    every steep-but-smooth thermocline gradient fires. (Measured on one cruise:
    naive 92 hits, with neighbour agreement 19 — the other 73 were real
    gradients.)

    :return: one row per suspect scan: ``scan_id, cast_id, cast_dir, depth,
        value, value_above, value_below, excursion, neighbour_gap``
    """
    c = _ident(column)
    return _read_sql(con, f"""
        WITH x AS (
          SELECT s.scan_id, s.cast_id, f.cast_dir, s.depth, s.{c} AS v,
                 LAG(s.{c})  OVER (PARTITION BY s.file_id, s.cast_id ORDER BY s.depth) AS v_above,
                 LEAD(s.{c}) OVER (PARTITION BY s.file_id, s.cast_id ORDER BY s.depth) AS v_below
          FROM ctd.v_scan_best s JOIN ctd.file f USING (file_id)
          WHERE s.study = %s AND s.{c} IS NOT NULL
        )
        SELECT scan_id, cast_id, cast_dir, depth,
               round(v::numeric, 4)                            AS value,
               round(v_above::numeric, 4)                      AS value_above,
               round(v_below::numeric, 4)                      AS value_below,
               round(abs(v - (v_above + v_below) / 2)::numeric, 4) AS excursion,
               round(abs(v_above - v_below)::numeric, 4)       AS neighbour_gap
        FROM x
        WHERE v_above IS NOT NULL AND v_below IS NOT NULL
          AND abs(v - (v_above + v_below) / 2) > %s
          AND abs(v_above - v_below)           < %s
        ORDER BY cast_id, depth
        """, (study, spike_threshold, neighbour_tol))


def cc_qc_sensor_pair(
    con,
    study: str,
    column1: str = "temp1",
    column2: str = "temp2",
    threshold: float = 0.05,
) -> "pd.DataFrame":
    """Primary vs secondary sensor disagreement (``ctd_sensor1_vs_sensor2``).

    The source's own ``*Q`` codes 1/2 mean "use primary"/"use secondary"
    precisely because one sensor of a pair can misbehave; a persistent gap
    between the pair is how that is spotted.

    :return: one row per scan where ``abs(col1 - col2) > threshold``
    """
    c1, c2 = _ident(column1), _ident(column2)
    return _read_sql(con, f"""
        SELECT s.scan_id, s.cast_id, f.cast_dir, s.depth,
               s.{c1} AS v1, s.{c2} AS v2,
               round(abs(s.{c1} - s.{c2})::numeric, 4) AS gap
        FROM ctd.v_scan_best s JOIN ctd.file f USING (file_id)
        WHERE s.study = %s AND s.{c1} IS NOT NULL AND s.{c2} IS NOT NULL
          AND abs(s.{c1} - s.{c2}) > %s
        ORDER BY gap DESC
        """, (study, threshold))


def cc_qc_range(
    con,
    study: str,
    column: str,
    valid_min: float | None = None,
    valid_max: float | None = None,
) -> "pd.DataFrame":
    """Values outside declared physical bounds (``ctd_value_out_of_range``).

    Bounds are deliberately generous — they catch the impossible (an unconverted
    ``-99`` sentinel, a scaling error), they do not police oceanography.

    :return: one row per out-of-bounds scan: ``scan_id, cast_id, depth, value``
    """
    c = _ident(column)
    viol = []
    if valid_min is not None:
        viol.append(f"s.{c} < %s")
    if valid_max is not None:
        viol.append(f"s.{c} > %s")
    if not viol:
        raise ValueError("give valid_min and/or valid_max")
    sql = f"""
        SELECT s.scan_id, s.cast_id, f.cast_dir, s.depth, s.{c} AS value
        FROM ctd.v_scan_best s JOIN ctd.file f USING (file_id)
        WHERE s.study = %s AND s.{c} IS NOT NULL AND ({' OR '.join(viol)})
        ORDER BY s.cast_id, s.depth
        """
    params = [study] + [b for b in (valid_min, valid_max) if b is not None]
    return _read_sql(con, sql, params)


# ── the ledger ───────────────────────────────────────────────────────────────

def cc_propose_flags(
    con,
    scan_ids: Iterable[int],
    variable: str,
    qual_code: int,
    reason: str,
    rule_key: str | None = None,
    proposed_value: float | None = None,
    commit: bool = True,
) -> int:
    """Propose QC flags: one ``ctd.flag`` row per scan × variable.

    Idempotent: a scan that already carries a ``proposed`` or ``accepted`` flag
    for this variable (any proposer) is skipped, so re-running a notebook does
    not stack duplicates. Curators then accept/reject in SQL or pgAdmin; only
    **accepted** flags affect ``ctd.v_scan_qc`` / ``ctd.v_scan_clean``.

    :param qual_code: IODE code from ``ctd.qual_code`` — 3 probably_bad, 4 bad,
        5 changed (requires ``proposed_value``), 9 missing, …
    :param rule_key: the QC rule that proposed it (e.g. ``"ctd_spike_v1"``),
        for provenance
    :return: number of flags actually inserted
    """
    ids = [int(i) for i in scan_ids]
    if not ids:
        return 0
    cur = con.execute("""
        INSERT INTO ctd.flag (scan_id, variable, qual_code, proposed_value, rule_key, reason)
        SELECT s.scan_id, %(var)s, %(code)s, %(val)s, %(rule)s, %(reason)s
        FROM ctd.scan s
        WHERE s.scan_id = ANY(%(ids)s)
          AND NOT EXISTS (
            SELECT 1 FROM ctd.flag f
            WHERE f.scan_id = s.scan_id AND f.variable = %(var)s
              AND f.status IN ('proposed', 'accepted'))
        """, {"var": _ident(variable), "code": qual_code, "val": proposed_value,
              "rule": rule_key, "reason": reason, "ids": ids})
    n = cur.rowcount
    if commit:
        con.commit()
    return n


def cc_flags(con, study: str | None = None, status: str | None = None) -> "pd.DataFrame":
    """The QC ledger, joined to its scans: who proposed what, where, and its fate.

    :param study: restrict to one cruise; default all
    :param status: ``proposed`` / ``accepted`` / ``rejected`` / ``withdrawn``; default all
    """
    conds, params = ["true"], []
    if study is not None:
        conds.append("fi.study = %s")
        params.append(study)
    if status is not None:
        conds.append("f.status = %s")
        params.append(status)
    return _read_sql(con, f"""
        SELECT f.flag_id, fi.study, s.cast_id, s.depth, f.variable, f.qual_code,
               q.label AS qual_label, f.proposed_value, f.rule_key, f.reason,
               f.status, f.created_by, f.created_at, f.reviewed_by, f.review_note
        FROM ctd.flag f
        JOIN ctd.qual_code q USING (qual_code)
        JOIN ctd.file fi ON fi.file_id = f.file_id
        LEFT JOIN ctd.scan s USING (scan_id)
        WHERE {' AND '.join(conds)}
        ORDER BY f.flag_id
        """, params)


# ── derived products ─────────────────────────────────────────────────────────

def cc_bin_1m(
    con,
    study: str,
    column: str = "tempave",
    cast_dir: str = "D",
    write_table: str | None = None,
    commit: bool = True,
) -> "pd.DataFrame":
    """Clean 1 m binned averages per cast, from ``ctd.v_scan_clean``.

    "Clean" means: accepted fixes substituted, accepted-bad values NULLed —
    exactly the ledger's verdicts and nothing else. Regenerable at any time,
    which is the point of keeping originals immutable.

    :param cast_dir: ``"D"`` downcast (default), ``"U"`` upcast, or ``"*"`` both
    :param write_table: also write the result to ``work.<write_table>``
        (replacing it), so colleagues can query it by name
    :return: DataFrame ``cast_id, cast_dir, depth_m, value, n, sd``
    """
    c = _ident(column)
    conds, params = ["s.study = %s"], [study]
    if cast_dir != "*":
        conds.append("f.cast_dir = %s")
        params.append(cast_dir)
    d = _read_sql(con, f"""
        SELECT s.cast_id, f.cast_dir, floor(s.depth)::int AS depth_m,
               round(avg(s.{c})::numeric, 4)        AS value,
               count(s.{c})                          AS n,
               round(stddev_samp(s.{c})::numeric, 4) AS sd
        FROM ctd.v_scan_clean s JOIN ctd.file f USING (file_id)
        WHERE {' AND '.join(conds)} AND s.{c} IS NOT NULL
        GROUP BY 1, 2, 3
        ORDER BY 1, 3
        """, params)
    if write_table is not None:
        t = _ident(write_table)
        con.execute(f"DROP TABLE IF EXISTS work.{t}")
        con.execute(f"""
            CREATE TABLE work.{t} (
              cast_id text, cast_dir text, depth_m int,
              value double precision, n int, sd double precision)""")
        with con.cursor().copy(
                f"COPY work.{t} (cast_id, cast_dir, depth_m, value, n, sd) FROM STDIN") as cp:
            for row in d.itertuples(index=False):
                cp.write_row([None if pd.isna(v) else v for v in row])
        from psycopg import sql as _sql
        con.execute(_sql.SQL("COMMENT ON TABLE work.{} IS {}").format(
            _sql.Identifier(t),
            _sql.Literal(f"1 m binned {c} for {study} ({cast_dir}) from ctd.v_scan_clean — regenerable; calcofi4py.cc_bin_1m")))
        if commit:
            con.commit()
    return d


# ── visualization (plotly) ───────────────────────────────────────────────────

def _px():
    try:
        import plotly.express as px
        return px
    except ImportError as e:  # pragma: no cover
        raise ImportError("viz helpers need plotly: pip install 'calcofi4py[viz]'") from e


def cc_station_map(casts: "pd.DataFrame", color: str = "cast_dir", title: str | None = None):
    """Map of cast positions, labeled by station, from :func:`cc_ctd_casts`.

    Casts without a position (``-99`` sentinels in the originals) are dropped
    from the map — they are still in the table.
    """
    px = _px()
    d = casts.dropna(subset=["lat", "lon"]).copy()
    d["station"] = d["sta_id"].fillna("?")
    fig = px.scatter_map(
        d, lat="lat", lon="lon", color=color,
        hover_name="cast_id",
        hover_data={"station": True, "datetime_utc": True, "depth_max": True,
                    "lat": ":.3f", "lon": ":.3f"},
        zoom=5, height=520, title=title)
    fig.update_layout(map_style="carto-positron",
                      margin=dict(l=0, r=0, t=40 if title else 0, b=0))
    return fig


def cc_profile_plot(
    scans: "pd.DataFrame",
    column: str = "tempave",
    cast_ids: Iterable[str] | None = None,
    flags: "pd.DataFrame | None" = None,
    units: str = "",
    title: str | None = None,
):
    """Depth profiles with down- and upcasts distinguished; optional flag overlay.

    :param scans: from :func:`cc_ctd_scans` (needs ``depth, cast_id, cast_dir``
        and ``column``)
    :param cast_ids: restrict to these casts (default: all in ``scans`` — one
        trace per cast × direction, thin, so a whole cruise reads as an envelope)
    :param flags: rows with ``scan_id`` (e.g. from :func:`cc_qc_spike` or
        :func:`cc_flags`) drawn as red × markers on top
    """
    px = _px()
    d = scans.dropna(subset=[column]).copy()
    if cast_ids is not None:
        d = d[d.cast_id.isin(set(cast_ids))]
    d["direction"] = d["cast_dir"].map({"D": "down", "U": "up"})
    fig = px.line(
        d.sort_values(["cast_id", "depth"]),
        x=column, y="depth", color="direction", line_group="cast_id",
        color_discrete_map={"down": "#1f77b4", "up": "#ff7f0e"},
        hover_data={"cast_id": True, "depth": ":.1f", column: ":.3f"},
        height=600, title=title,
        labels={column: f"{column} ({units})" if units else column, "depth": "depth (m)"})
    fig.update_traces(line=dict(width=1), opacity=0.5)
    if flags is not None and len(flags):
        f = d[d.scan_id.isin(set(flags.scan_id))]
        fig.add_scatter(x=f[column], y=f.depth, mode="markers", name="flagged",
                        marker=dict(symbol="x", size=9, color="crimson"))
    fig.update_yaxes(autorange="reversed")
    return fig


def cc_section_plot(
    scans: "pd.DataFrame",
    casts: "pd.DataFrame",
    column: str = "tempave",
    units: str = "",
    title: str | None = None,
):
    """Section through the cruise: cast sequence (x) × depth (y), colored by value.

    Downcasts only, ordered by time — a quick-look transect, not an interpolated
    product (each vertical stripe is one cast's scans).
    """
    px = _px()
    order = (casts[casts.cast_dir == "D"]
             .sort_values("datetime_utc")["cast_id"].tolist())
    d = scans[(scans.cast_dir == "D") & scans[column].notna()].copy()
    d = d[d.cast_id.isin(order)]
    d["cast_order"] = d["cast_id"].map({c: i for i, c in enumerate(order)})
    fig = px.scatter(
        d, x="cast_order", y="depth", color=column,
        color_continuous_scale="Viridis", height=520, title=title,
        hover_data={"cast_id": True, "depth": ":.1f", column: ":.3f"},
        labels={"cast_order": "cast (time order)", "depth": "depth (m)",
                column: f"{column} ({units})" if units else column})
    fig.update_traces(marker=dict(size=3))
    fig.update_yaxes(autorange="reversed")
    return fig
