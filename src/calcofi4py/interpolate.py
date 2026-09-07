"""The Explorer's Contours lens, as a function (plan 2026-09-07 § D31–D33, D39).

One algorithm in three runtimes: the browser's ``src/contour.worker.ts``, ``calcofi4r::cc_interpolate()``
and this module reproduce the same numbers from the same point set — pinned by
``tests/fixtures/contour_fixture.json``, which the browser's own code writes
(``explore/scripts/parity/contour_fixture.mjs``) and both packages' tests read. Deliberately not
scipy / pykrige / pygam: those would give a *different* surface, and the point is that a figure made in
Python matches the map.

- ``idw`` inverse-distance weighting, power 1.3, radius 200 km, 5 km smoothing (parity with
  ``terra::interpIDW`` as the superseded Contour Explorer used it); no error surface
- ``ok`` ordinary kriging: an exponential variogram fitted by weighted least squares over a small grid,
  the augmented system inverted once; the kriging standard deviation is the error; leave-one-out by
  Dubrule (1983)
- ``tps`` a thin-plate spline (r² log r + a linear trend, mgcv's ``s(lon, lat)`` basis) with the ridge
  picked by GCV over nine values; its standard error from the smoother rows
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Sequence

Method = Literal["ok", "idw", "tps"]


def _np():
    try:
        import numpy as np
    except ImportError as e:  # pragma: no cover
        raise ImportError("calcofi4py.interpolate() needs numpy: pip install 'calcofi4py[interp]'") from e
    return np


@dataclass
class Grid:
    lon0: float
    lon1: float
    lat_s: float
    lat_n: float
    nx: int
    ny: int
    cell_deg: float


@dataclass
class Fit:
    n: int
    n_cells: int
    loo: float
    vg: dict | None = None
    edf: float | None = None


@dataclass
class Surface:
    """``values`` / ``se`` are ``ny × nx`` arrays, **row 0 = north**; ``NaN`` where the mask blanks a cell."""

    grid: Grid
    values: "object"
    se: "object | None"
    fit: Fit
    method: str
    extent_3857: tuple[float, float, float, float] = field(default=(0.0, 0.0, 0.0, 0.0))


def _merc(np, lat):
    return np.log(np.tan(np.pi / 4 + lat * np.pi / 360))


def _imerc(np, y):
    return (2 * np.arctan(np.exp(y)) - np.pi / 2) * 180 / np.pi


def _variogram(np, X, Y, Z):
    """the empirical semivariogram (15 bins to half the max distance) and an exponential model by WLS"""
    n = len(X)
    nb = 15
    iu, ju = np.triu_indices(n, 1)
    d = np.hypot(X[iu] - X[ju], Y[iu] - Y[ju])
    g = 0.5 * (Z[iu] - Z[ju]) ** 2
    dmax = d.max() / 2
    keep = d < dmax
    b = np.floor(d[keep] / dmax * nb).astype(int)
    bs = np.bincount(b, weights=g[keep], minlength=nb)
    bn = np.bincount(b, minlength=nb)
    used = bn > 0
    h = (np.arange(nb)[used] + 0.5) * dmax / nb
    ge = bs[used] / bn[used]
    ne = bn[used].astype(float)
    svar = max(1e-9, float(ge[-1]))
    best = (np.inf, 0.0, svar, dmax / 3)
    for nug in (0, 0.05, 0.1, 0.2, 0.3):
        for rg in (0.1, 0.2, 0.35, 0.5, 0.75, 1, 1.5):
            for sill in (0.6, 0.8, 1, 1.2, 1.5):
                a = rg * dmax
                c0 = nug * svar
                c1 = max(1e-9, sill * svar - c0)
                m = c0 + c1 * (1 - np.exp(-h / a))
                ss = float(np.sum(ne * (ge - m) ** 2 / (m * m)))
                if ss < best[0]:
                    best = (ss, c0, c1, a)
    return {"nugget": best[1], "psill": best[2], "range": best[3]}


def interpolate(
    points: Iterable[Mapping[str, float]] | Sequence[Sequence[float]] | "object",
    method: Method = "ok",
    cell_deg: float = 0.06,
    mask_km: float = 60.0,
    se: bool = True,
) -> Surface:
    """Interpolate point values to a surface, exactly as the Explorer's Contours lens does.

    The same algorithm as ``calcofi.io/explore`` (``lens=contour``) and ``calcofi4r::cc_interpolate()``,
    so a surface drawn in Python matches the map cell for cell: a grid of ``cell_deg`` degrees of
    longitude whose rows are evenly spaced in Web-Mercator y, a local equirectangular km frame for the
    distances, and no value farther than ``mask_km`` from every point — the surface never extrapolates.

    ``points``: an iterable of mappings with ``lon``, ``lat``, ``z`` (a list of dicts, a pandas
    DataFrame's ``to_dict("records")``, or a DataFrame itself), or an ``(n, 3)`` sequence. Rows with a
    missing value are dropped. ``method``: ``"ok"`` (default; the kriging SD is the error surface),
    ``"idw"`` (no error surface) or ``"tps"`` (its standard error is the error surface). ``se=False``
    skips the error surface, the slow part.
    """
    np = _np()
    if hasattr(points, "to_dict"):  # a pandas DataFrame
        points = points.to_dict("records")
    rows = [(p["lon"], p["lat"], p["z"]) if isinstance(p, Mapping) else tuple(p[:3]) for p in points]
    P = np.asarray(rows, dtype=float)
    P = P[np.isfinite(P).all(axis=1)]
    n = len(P)
    if n < 4:
        raise ValueError("interpolate() needs at least 4 points")
    if method not in ("ok", "idw", "tps"):
        raise ValueError(f"method must be ok, idw or tps, not {method!r}")
    lon, lat, z = P[:, 0], P[:, 1], P[:, 2]
    R = np.pi / 180
    # the grid: rows evenly spaced in Web-Mercator y, so the bitmap the map stretches between the bounds is exact
    lo0, lo1, la0, la1 = lon.min(), lon.max(), lat.min(), lat.max()
    pad, s = 0.7, cell_deg * R
    lon0 = lo0 - pad
    yN, yS = _merc(np, la1 + pad), _merc(np, la0 - pad)
    nx = int(np.ceil((lo1 + pad - lon0) * R / s))
    ny = int(np.ceil((yN - yS) / s))
    grid = Grid(lon0=float(lon0), lon1=float(lon0 + nx * s / R), lat_s=float(_imerc(np, yN - ny * s)), lat_n=float(_imerc(np, yN)), nx=nx, ny=ny, cell_deg=cell_deg)
    # a local equirectangular km frame about the points' centre
    lonc, latc = (lo0 + lo1) / 2, (la0 + la1) / 2
    kx, ky = 111.32 * np.cos(latc * R), 110.57
    X, Y = (lon - lonc) * kx, (lat - latc) * ky
    cx = (lon0 + (np.arange(nx) + 0.5) * s / R - lonc) * kx           # cell centres, x per column
    cy = (_imerc(np, yN - (np.arange(ny) + 0.5) * s) - latc) * ky     # y per row, north first
    values = np.full((ny, nx), np.nan)
    se_m = np.full((ny, nx), np.nan) if (se and method != "idw") else None
    fit = Fit(n=n, n_cells=0, loo=float("nan"))
    r2 = mask_km * mask_km

    def d2_row(j):
        return (cx[:, None] - X[None, :]) ** 2 + (cy[j] - Y[None, :]) ** 2

    if method == "idw":
        power, rad2, sm2 = 1.3, 200.0 ** 2, 5.0 ** 2
        for j in range(ny):
            d2 = d2_row(j)
            msk = (d2 <= r2).any(axis=1)
            if not msk.any():
                continue
            w = (d2 + sm2) ** (-power / 2)
            w[d2 > rad2] = 0
            sw = w.sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                v = (w @ z) / sw
            v[sw == 0] = np.nan
            values[j, msk] = v[msk]
            fit.n_cells += int(msk.sum())
        Dp = (X[:, None] - X[None, :]) ** 2 + (Y[:, None] - Y[None, :]) ** 2
        w = (Dp + sm2) ** (-power / 2)
        np.fill_diagonal(w, 0)
        fit.loo = float(np.sqrt(np.mean(((w @ z) / w.sum(axis=1) - z) ** 2)))
    elif method == "ok":
        vg = _variogram(np, X, Y, z)
        fit.vg = vg
        m = n + 1
        cov = lambda d: vg["psill"] * np.exp(-d / vg["range"])  # noqa: E731
        Dp = np.hypot(X[:, None] - X[None, :], Y[:, None] - Y[None, :])
        K = np.ones((m, m))
        K[:n, :n] = cov(Dp)
        K[np.arange(n), np.arange(n)] = vg["psill"] + vg["nugget"] + 1e-6 * vg["psill"]
        K[n, n] = 0
        Ki = np.linalg.inv(K)
        wz = Ki[:, :n] @ z
        fit.loo = float(np.sqrt(np.mean((wz[:n] / np.diag(Ki)[:n]) ** 2)))
        for j in range(ny):
            d2 = d2_row(j)
            msk = (d2 <= r2).any(axis=1)
            if not msk.any():
                continue
            kv = cov(np.sqrt(d2))
            values[j, msk] = (kv @ wz[:n] + wz[n])[msk]
            fit.n_cells += int(msk.sum())
            if se_m is not None:
                kva = np.hstack([kv[msk], np.ones((int(msk.sum()), 1))])
                lam = kva @ Ki
                v = vg["psill"] + vg["nugget"] - (lam * kva).sum(axis=1)
                se_m[j, msk] = np.sqrt(np.maximum(0, v))
    else:
        m = n + 3

        def ker(r):
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(r > 0, r * r * np.log(np.where(r > 0, r, 1)), 0.0)

        Dp = np.hypot(X[:, None] - X[None, :], Y[:, None] - Y[None, :])
        K0 = np.zeros((m, m))
        K0[:n, :n] = ker(Dp)
        K0[:n, n] = K0[n, :n] = 1
        K0[:n, n + 1] = K0[n + 1, :n] = X
        K0[:n, n + 2] = K0[n + 2, :n] = Y
        scale = float(np.abs(K0[:n, :]).max())
        best = None
        for lam in (1e-4, 1e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1, 3, 10):
            lam = lam * scale
            K = K0.copy()
            K[np.arange(n), np.arange(n)] += lam
            Ki = np.linalg.inv(K)
            c = Ki[:, :n] @ z
            e = c[:n] * lam
            kd = np.diag(Ki)[:n]
            rss = float(np.sum(e * e))
            sse = float(np.sum((e / (lam * kd)) ** 2))
            tr = float(np.sum(1 - lam * kd))
            gcv = (sse / n) / (1 - tr / n) ** 2
            if best is None or gcv < best[0]:
                best = (gcv, lam, c, Ki, float(np.sqrt(sse / n)), tr, rss)
        _, lam, c, Ki, fit.loo, fit.edf, rss = best
        sigma2 = rss / max(1, n - fit.edf)
        for j in range(ny):
            d2 = d2_row(j)
            msk = (d2 <= r2).any(axis=1)
            if not msk.any():
                continue
            B = np.hstack([ker(np.sqrt(d2)), np.ones((nx, 1)), cx[:, None], np.full((nx, 1), cy[j])])
            values[j, msk] = (B @ c)[msk]
            fit.n_cells += int(msk.sum())
            if se_m is not None:
                W = B[msk] @ Ki[:n, :].T   # (cells × n): each column a smoother weight
                se_m[j, msk] = np.sqrt(sigma2 * (W * W).sum(axis=1))
    Rm = 6378137.0
    ext = (grid.lon0 * R * Rm, grid.lon1 * R * Rm, float(_merc(np, grid.lat_s)) * Rm, float(_merc(np, grid.lat_n)) * Rm)
    return Surface(grid=grid, values=values, se=se_m, fit=fit, method=method, extent_3857=ext)
