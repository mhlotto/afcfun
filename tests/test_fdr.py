import math

from e0_inspect import benjamini_hochberg


def test_benjamini_hochberg_adjustment() -> None:
    p_values = {
        "a": 0.01,
        "b": 0.04,
        "c": 0.03,
        "d": 0.002,
        "e": None,
    }
    q_values = benjamini_hochberg(p_values)

    assert math.isclose(q_values["d"], 0.008, rel_tol=1e-9)
    assert math.isclose(q_values["a"], 0.02, rel_tol=1e-9)
    assert math.isclose(q_values["c"], 0.04, rel_tol=1e-9)
    assert math.isclose(q_values["b"], 0.04, rel_tol=1e-9)
    assert q_values["e"] is None
