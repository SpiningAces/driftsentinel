"""Library API smoke tests — clamp behavior and version export."""
import driftsentinel as ds


def test_version_exported():
    assert isinstance(ds.__version__, str)
    assert ds.__version__ == "0.0.1"


def test_clean_spec_scores_100():
    a = ds.compute_adi(
        {"oasdiff": {}, "vacuum": {"by_severity": {}}, "schemathesis": {}},
        weights=ds.ADI_DEFAULTS["weights"],
        caps=ds.ADI_DEFAULTS["caps"],
    )
    assert a["score"] == 100.0


def test_apocalypse_clamps_to_zero():
    a = ds.compute_adi(
        {
            "oasdiff": {"breaking_count": 9999},
            "vacuum": {"by_severity": {"error": 9999, "warn": 9999}},
            "schemathesis": {"failures": 9999},
        },
        weights=ds.ADI_DEFAULTS["weights"],
        caps=ds.ADI_DEFAULTS["caps"],
    )
    assert a["score"] == 0.0


def test_one_breaking_change():
    a = ds.compute_adi(
        {"oasdiff": {"breaking_count": 1}, "vacuum": {"by_severity": {}}, "schemathesis": {}},
        weights=ds.ADI_DEFAULTS["weights"],
        caps=ds.ADI_DEFAULTS["caps"],
    )
    assert a["score"] == 90.0


def test_negative_inputs_defensive_clamp():
    a = ds.compute_adi(
        {"oasdiff": {"breaking_count": -5}, "vacuum": {"by_severity": {}}, "schemathesis": {}},
        weights=ds.ADI_DEFAULTS["weights"],
        caps=ds.ADI_DEFAULTS["caps"],
    )
    assert a["score"] == 100.0


def test_dv_real_world_score():
    """Calibration: real Deep Vector internal API readings."""
    a = ds.compute_adi(
        {
            "oasdiff": {"breaking_count": 0},
            "vacuum": {"by_severity": {"error": 1, "warn": 736}},
            "schemathesis": {"failures": 18},
        },
        weights=ds.ADI_DEFAULTS["weights"],
        caps=ds.ADI_DEFAULTS["caps"],
    )
    assert a["score"] == 50.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
    print("all smoke tests pass")
