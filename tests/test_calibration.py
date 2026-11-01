import pytest

from app.calibration import apply_platt, fit_platt


def test_platt_calibration_preserves_order_and_bounds():
    scale, offset = fit_platt([0.05, 0.2, 0.8, 0.95], [0, 0, 1, 1])
    calibrated = [apply_platt(value, scale, offset) for value in [0.05, 0.2, 0.8, 0.95]]
    assert all(0 < value < 1 for value in calibrated)
    assert calibrated == sorted(calibrated)
    assert calibrated[0] < 0.5 < calibrated[-1]


def test_calibration_rejects_single_class():
    with pytest.raises(ValueError):
        fit_platt([0.1, 0.2], [0, 0])
