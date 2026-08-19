"""calcofi4py — CalCOFI Python helpers, the thin sibling of calcofi4r.

Two data stores, two verbs:

- **Public releases** (immutable Parquet on GCS, no credentials):
  ``cc_get_db()`` -> DuckDB connection with every release table as a view;
  ``cc_query(sql)`` for one-shots; ``cc_list_versions()`` / ``cc_catalog()``.
- **The CTD team's PostgreSQL working database** (private, over SSH):
  ``cc_pg_connect()`` (psycopg; role + password from ~/.pgpass),
  ``cc_pg_tunnel()`` / ``cc_pg_tunnel_close()`` (background `ssh -N`),
  ``cc_pg_attach()`` (the PG database inside a DuckDB connection, so release
  Parquet and ``pg.ctd.*`` join in one query).

Docs: https://calcofi.io/docs/server-access.html and
https://calcofi.io/docs/data-access.html
"""

from .release import (
    cc_catalog,
    cc_get_db,
    cc_list_versions,
    cc_query,
    cc_resolve_version,
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
    "cc_catalog",
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
]
__version__ = "0.1.0"
