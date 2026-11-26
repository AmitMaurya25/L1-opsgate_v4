import pytest
from tests.safety_cases import CASES

@pytest.mark.parametrize('n,name,scenario,expected,fn', CASES, ids=[c[1] for c in CASES])
def test_safety(n, name, scenario, expected, fn, tmp_path):
    observed, ok = fn(tmp_path)
    assert ok, observed
