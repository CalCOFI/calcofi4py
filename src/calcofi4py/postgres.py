"""Connect to the CalCOFI multi-user PostgreSQL database (CTD QA/QC).

Mirrors ``calcofi4r::cc_pg_connect()`` / ``cc_pg_tunnel()`` / ``cc_pg_attach()``
(calcofi4r/R/postgres.R) — keep the two implementations in step.

The database (``calcofi``: schemas ``ctd`` / ``work`` / your own) is private and
reachable only over SSH. Secrets never appear in code: the password comes from
libpq's ``~/.pgpass`` (Windows: ``%APPDATA%\\postgresql\\pgpass.conf``), which
psycopg reads natively. Account + tunnel + .pgpass setup:
https://calcofi.io/docs/server-access.html
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psycopg

_TUNNELS: dict[str, subprocess.Popen] = {}


def _nz(x: str | None) -> str | None:
    return x if x else None


def cc_on_server() -> bool:
    """True inside the CalCOFI server containers, where the DB is host ``postgis``."""
    return bool(os.environ.get("CALCOFI_ON_SERVER")) or (
        Path("/share/github/CalCOFI").is_dir() and platform.system() == "Linux"
    )


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _pgpass_path() -> Path:
    f = os.environ.get("PGPASSFILE")
    if f:
        return Path(f)
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", "")) / "postgresql" / "pgpass.conf"
    return Path.home() / ".pgpass"


def cc_pgpass_user(host: str, port: int | str, dbname: str) -> str | None:
    """The role name recorded in ``~/.pgpass`` for host:port:dbname (first match).

    Lets a user who copied the file from the server connect with no ``PGUSER``.
    Format per line: ``host:port:database:user:password`` (password may contain
    ``:``; ``*`` wildcards; ``#`` comments).
    """
    f = _pgpass_path()
    if not f.is_file():
        return None
    for ln in f.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(":")
        if len(parts) < 5:
            continue
        h, p, d, u = parts[0], parts[1], parts[2], parts[3]
        if (
            h in ("*", host)
            and p in ("*", str(port))
            and d in ("*", dbname)
            and u
        ):
            return u
    return None


def cc_pg_connect(
    dbname: str = "calcofi",
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    tunnel: bool = False,
    **kwargs,
) -> psycopg.Connection:
    """psycopg connection to the CalCOFI PostgreSQL database, defaults resolved.

    - **host**: ``postgis`` on the CalCOFI server (RStudio/Jupyter there),
      otherwise ``localhost`` — the local end of your SSH tunnel. ``PGHOST`` overrides.
    - **user**: ``PGUSER`` if set, else the role in your ``~/.pgpass`` for this
      host/port/db, else your OS user name.
    - **password**: never passed — libpq reads ``~/.pgpass``.
    - ``tunnel=True`` starts ``ssh -N calcofi`` for you first (off-server only).

    >>> con = cc_pg_connect(tunnel=True)
    >>> con.execute("SELECT count(*) FROM ctd.cast").fetchone()
    """
    host = host or _nz(os.environ.get("PGHOST")) or ("postgis" if cc_on_server() else "localhost")
    port = int(port or _nz(os.environ.get("PGPORT")) or 5432)
    if tunnel and host in ("localhost", "127.0.0.1"):
        cc_pg_tunnel(local_port=port)
    user = (
        user
        or _nz(os.environ.get("PGUSER"))
        or cc_pgpass_user(host, port, dbname)
        or os.environ.get("USER", os.environ.get("USERNAME", ""))
    )
    return psycopg.connect(dbname=dbname, host=host, port=port, user=user, **kwargs)


def cc_pg_tunnel(
    ssh_host: str = "calcofi",
    local_port: int = 5432,
    remote_port: int = 5432,
    wait: float = 10.0,
) -> subprocess.Popen | None:
    """Open ``ssh -N -L {local_port}:localhost:{remote_port} {ssh_host}`` in the background.

    Uses your ``~/.ssh/config`` alias (host, user, key) so no credentials are
    handled here; Windows 10+ has ``ssh.exe`` built in. Reused while alive;
    close with :func:`cc_pg_tunnel_close`. If something already listens on
    ``local_port`` it is left alone (use ``local_port=15432`` in both places if
    that is not the CalCOFI tunnel).
    """
    key = f"{ssh_host}:{local_port}"
    p = _TUNNELS.get(key)
    if p is not None and p.poll() is None:
        return p
    if _port_open("127.0.0.1", local_port):
        print(
            f"something already listens on localhost:{local_port} — using it as-is. "
            "If that is not the CalCOFI server, use local_port=15432."
        )
        return None
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError(
            "no `ssh` on PATH (Windows: Settings > Optional features > OpenSSH Client)"
        )
    p = subprocess.Popen(  # noqa: S603
        [ssh, "-N", "-o", "ExitOnForwardFailure=yes", "-o", "BatchMode=yes",
         "-L", f"{local_port}:localhost:{remote_port}", ssh_host],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    t0 = time.monotonic()
    while not _port_open("127.0.0.1", local_port):
        if p.poll() is not None:
            err = (p.stderr.read() if p.stderr else b"").decode()
            raise RuntimeError(
                f"ssh exited before the tunnel came up:\n{err}\n"
                f"Check `ssh {ssh_host}` works in a terminal first."
            )
        if time.monotonic() - t0 > wait:
            p.kill()
            raise TimeoutError(f"tunnel did not open within {wait} s")
        time.sleep(0.25)
    _TUNNELS[key] = p
    print(f"SSH tunnel up: localhost:{local_port} -> {ssh_host}:{remote_port}")
    return p


def cc_pg_tunnel_close(ssh_host: str = "calcofi", local_port: int = 5432) -> None:
    """Stop a tunnel started by :func:`cc_pg_tunnel`."""
    p = _TUNNELS.pop(f"{ssh_host}:{local_port}", None)
    if p is not None and p.poll() is None:
        p.kill()
        print(f"tunnel closed ({ssh_host}:{local_port})")


def cc_pg_attach(
    con,
    alias: str = "pg",
    dbname: str = "calcofi",
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    read_only: bool = True,
):
    """ATTACH the PostgreSQL database inside a DuckDB connection.

    One DuckDB query can then join the public release tables (from
    :func:`calcofi4py.cc_get_db`) with the team's PostgreSQL tables
    (``pg.ctd.flag``, ``pg.work.*``). The password comes from ``~/.pgpass``
    (DuckDB's postgres extension uses libpq). ``read_only=False`` also allows
    bulk writes from Parquet into PostgreSQL.

    >>> con = cc_get_db()
    >>> cc_pg_attach(con)
    >>> con.sql("SELECT count(*) FROM pg.ctd.flag").fetchone()
    """
    host = host or _nz(os.environ.get("PGHOST")) or ("postgis" if cc_on_server() else "localhost")
    port = int(port or _nz(os.environ.get("PGPORT")) or 5432)
    user = (
        user
        or _nz(os.environ.get("PGUSER"))
        or cc_pgpass_user(host, port, dbname)
        or os.environ.get("USER", os.environ.get("USERNAME", ""))
    )
    con.execute("INSTALL postgres; LOAD postgres;")
    opts = "TYPE postgres" + (", READ_ONLY" if read_only else "")
    con.execute(
        f"ATTACH IF NOT EXISTS 'dbname={dbname} host={host} port={port} user={user}' "
        f"AS {alias} ({opts})"
    )
    return con
