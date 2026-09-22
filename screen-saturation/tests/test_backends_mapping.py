"""Tests mapping grading / DVC."""

from saturation.backends.nvidia import NvidiaVibranceBackend
from saturation.grading import (
    PRESETS,
    build_gamma_lut_1024,
    vibrance_to_saturation_factor,
)
from saturation.matrix import slider_to_saturation


def test_slider_to_sat():
    assert slider_to_saturation(100) == 1.0
    assert slider_to_saturation(0) == 0.0
    assert slider_to_saturation(200) == 2.0


def test_nvidia_dvc_mapping():
    assert NvidiaVibranceBackend._sat_to_dvc(0.0, 0, 63, 50) == 0
    assert NvidiaVibranceBackend._sat_to_dvc(1.0, 0, 63, 50) == 50
    assert NvidiaVibranceBackend._sat_to_dvc(2.0, 0, 63, 50) == 63


def test_vibrance_stays_mild():
    # Même à vibrance max UI, on ne dépasse pas 1.25× le défaut
    assert vibrance_to_saturation_factor(1.0) <= 1.25
    assert abs(vibrance_to_saturation_factor(0.5) - 1.0) < 1e-6


def test_naturel_lut_not_identity():
    lut = build_gamma_lut_1024(PRESETS["Naturel"])
    assert len(lut) == 1024
    # Le milieu doit bouger un peu vs 0.5 grâce à la présence
    assert abs(lut[512][0] - 0.5) > 0.001


if __name__ == "__main__":
    test_slider_to_sat()
    test_nvidia_dvc_mapping()
    test_vibrance_stays_mild()
    test_naturel_lut_not_identity()
    print("OK")
