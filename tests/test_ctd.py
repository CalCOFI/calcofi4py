"""Pure-logic tests for the CTD helpers (no server needed)."""
import pytest

from calcofi4py.ctd import _ident


def test_ident_accepts_snake_case():
    assert _ident("tempave") == "tempave"
    assert _ident("salt1_corr") == "salt1_corr"


@pytest.mark.parametrize("bad", ["Temp1", "temp ave", "temp;drop", "1temp", "", "temp-ave"])
def test_ident_rejects_injection_shapes(bad):
    with pytest.raises(ValueError):
        _ident(bad)


def test_qc_range_requires_a_bound():
    from calcofi4py.ctd import cc_qc_range
    with pytest.raises(ValueError):
        cc_qc_range(None, "2607SH", "tempave")
