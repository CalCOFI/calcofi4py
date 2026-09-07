"""interpolate() is one algorithm in three runtimes: tests/fixtures/contour_fixture.json is written by the
browser's own interpolator (explore/scripts/parity/contour_fixture.mjs from src/contour.worker.ts) and shared
byte-for-byte with calcofi4r/tests/testthat/fixtures/contour_fixture.json; every cell of every surface must agree."""
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
from calcofi4py import interpolate  # noqa: E402

FX = json.loads((Path(__file__).parent / "fixtures" / "contour_fixture.json").read_text())


def as_arr(v, g):
    return np.array([np.nan if x is None else x for x in v], dtype=float).reshape(g["ny"], g["nx"])


def test_grid_matches_the_browser():
    s = interpolate(FX["points"], "idw", cell_deg=FX["params"]["cellDeg"], mask_km=FX["params"]["maskKm"])
    g = FX["grid"]
    assert (s.grid.nx, s.grid.ny) == (g["nx"], g["ny"])
    assert s.grid.lon0 == pytest.approx(g["lon0"], abs=1e-9) and s.grid.lon1 == pytest.approx(g["lon1"], abs=1e-9)
    assert s.grid.lat_s == pytest.approx(g["latS"], abs=1e-9) and s.grid.lat_n == pytest.approx(g["latN"], abs=1e-9)
    assert s.fit.n_cells == FX["methods"]["idw"]["fit"]["nCells"]
    assert np.array_equal(np.isnan(s.values), np.isnan(as_arr(FX["methods"]["idw"]["values"], g)))


@pytest.mark.parametrize("key", list(FX["methods"]))
def test_surface_matches_the_browser_cell_for_cell(key):
    f = FX["methods"][key]
    method = f["method"]
    s = interpolate(FX["points"], method, cell_deg=FX["params"]["cellDeg"], mask_km=FX["params"]["maskKm"], se=True, nmax=f["nmax"])
    assert s.fit.nmax == f["nmax"]
    assert (s.fit.n, s.fit.n_cells) == (f["fit"]["n"], f["fit"]["nCells"])
    assert s.fit.loo == pytest.approx(f["fit"]["loo"], abs=1e-5)
    np.testing.assert_allclose(s.values, as_arr(f["values"], FX["grid"]), atol=1e-5, equal_nan=True)  # the fixture is rounded to 6 dp
    if method == "idw":
        assert s.se is None
    else:
        np.testing.assert_allclose(s.se, as_arr(f["se"], FX["grid"]), atol=1e-5, equal_nan=True)
    if method == "ok":
        for k in ("nugget", "psill", "range"):
            assert s.fit.vg[k] == pytest.approx(f["fit"]["vg"][k], abs=1e-5)
    if method == "tps":
        assert s.fit.edf == pytest.approx(f["fit"]["edf"], abs=1e-5)


def test_mask_and_inputs():
    s = interpolate(FX["points"], "ok", cell_deg=0.25, mask_km=20, se=False)
    assert np.isnan(s.values).any() and s.se is None
    assert s.fit.n_cells < FX["methods"]["ok"]["fit"]["nCells"]
    with pytest.raises(ValueError):
        interpolate(FX["points"][:3], "ok")
    with pytest.raises(ValueError):
        interpolate(FX["points"], "gam")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        interpolate(FX["points"], "tps", nmax=8)
    from calcofi4py.interpolate import lcg_sample
    assert lcg_sample(100, 30, 2)[:5] == [23, 46, 20, 74, 72]  # the browser's draw (0-based; R reads it 1-based)
    pd = pytest.importorskip("pandas")
    s2 = interpolate(pd.DataFrame(FX["points"]), "idw", cell_deg=0.25)
    np.testing.assert_allclose(s2.values, interpolate(FX["points"], "idw", cell_deg=0.25).values, equal_nan=True)
