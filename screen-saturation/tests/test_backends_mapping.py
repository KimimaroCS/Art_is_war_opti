"""Tests mapping saturation → niveau GPU."""

from saturation.backends.nvidia import NvidiaVibranceBackend
from saturation.matrix import slider_to_saturation


def test_slider_to_sat():
    assert slider_to_saturation(100) == 1.0
    assert slider_to_saturation(0) == 0.0
    assert slider_to_saturation(200) == 2.0


def test_nvidia_level_mapping():
    # min=0, default=50, max=63 (valeurs DVC typiques)
    assert NvidiaVibranceBackend._saturation_to_level(0.0, 0, 63, 50) == 0
    assert NvidiaVibranceBackend._saturation_to_level(1.0, 0, 63, 50) == 50
    assert NvidiaVibranceBackend._saturation_to_level(2.0, 0, 63, 50) == 63
    mid = NvidiaVibranceBackend._saturation_to_level(0.5, 0, 63, 50)
    assert mid == 25


if __name__ == "__main__":
    test_slider_to_sat()
    test_nvidia_level_mapping()
    print("OK")
