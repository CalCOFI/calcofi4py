"""calcofi4py — CalCOFI Python helpers, the thin sibling of calcofi4r.

Two data stores, two verbs:

- **Public releases** (immutable Parquet on GCS, no credentials):
  ``cc_get_db()`` -> DuckDB connection with every release table as a view;
  ``cc_query(sql)`` for one-shots; ``cc_list_versions()`` / ``cc_catalog()``;
  ``release_sources()`` — a catalog entry's parquet URLs (content-addressed since v2026.09);
  ``qual_ok_sql()`` — the WHERE predicate that drops flagged (suspect/bad) values.
- **CTD QA/QC** (schema ``ctd`` in PostgreSQL): ``cc_ctd_casts()`` / ``cc_ctd_scans()``,
  portable QC rules (``cc_qc_spike()``, ``cc_qc_sensor_pair()``, ``cc_qc_range()``),
  the flag ledger (``cc_propose_flags()`` / ``cc_flags()`` / ``cc_withdraw_flags()``), clean products
  (``cc_bin_1m()``), and plotly viz (``cc_station_map()``, ``cc_profile_plot()``,
  ``cc_section_plot()``).
- **The CTD team's PostgreSQL working database** (private, over SSH):
  ``cc_pg_connect()`` (psycopg; role + password from ~/.pgpass),
  ``cc_pg_tunnel()`` / ``cc_pg_tunnel_close()`` (background `ssh -N`),
  ``cc_pg_attach()`` (the PG database inside a DuckDB connection, so release
  Parquet and ``pg.ctd.*`` join in one query).

Docs: https://calcofi.io/docs/server-access.html and
https://calcofi.io/docs/data-access.html
"""

from .session import cc_session_info
from .release import (
    QUAL_EXCLUDE,
    RetiredVersionError,
    catalog_views,
    cc_catalog,
    cc_get_db,
    cc_list_versions,
    cc_query,
    cc_resolve_version,
    qual_ok_sql,
    density_sql,
    default_stage,
    default_denominator,
    read_parquet_sql,
    release_sources,
    view_sql,
    view_tables,
)
from .ctd import (
    cc_bin_1m,
    cc_ctd_casts,
    cc_ctd_scans,
    cc_flags,
    cc_flag_summary,
    cc_profile_explorer,
    cc_profile_plot,
    cc_propose_flags,
    cc_withdraw_flags,
    cc_qc_range,
    cc_qc_sensor_pair,
    cc_qc_spike,
    cc_section_plot,
    cc_station_map,
)
from .postgres import (
    cc_on_server,
    cc_pg_attach,
    cc_pg_connect,
    cc_pg_tunnel,
    cc_pg_tunnel_close,
    cc_pgpass_user,
)

__all__ = [
    "QUAL_EXCLUDE",
    "cc_bin_1m",
    "cc_catalog",
    "cc_ctd_casts",
    "cc_ctd_scans",
    "cc_flag_summary",
    "cc_flags",
    "cc_profile_explorer",
    "cc_profile_plot",
    "cc_propose_flags",
    "cc_withdraw_flags",
    "cc_qc_range",
    "cc_qc_sensor_pair",
    "cc_qc_spike",
    "cc_section_plot",
    "cc_station_map",
    "cc_get_db",
    "cc_list_versions",
    "cc_on_server",
    "cc_pg_attach",
    "cc_pg_connect",
    "cc_pg_tunnel",
    "cc_pg_tunnel_close",
    "cc_pgpass_user",
    "cc_query",
    "cc_resolve_version",
    "cc_session_info",
    "qual_ok_sql",
    "density_sql",
    "default_stage",
    "default_denominator",
    "read_parquet_sql",
    "release_sources",
    "catalog_views",
    "view_sql",
    "view_tables",
]
__version__ = "0.6.0"
