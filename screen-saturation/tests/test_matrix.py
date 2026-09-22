"""Tests unitaires (matrix) — exécutables hors Windows."""

from saturation.matrix import (
    identity_matrix,
    saturation_matrix,
    slider_to_saturation,
)


def test_identity_diagonal():
    m = identity_matrix()
    assert len(m) == 25
    for i in range(5):
        for j in range(5):
            expected = 1.0 if i == j else 0.0
            assert m[i * 5 + j] == expected


def test_saturation_one_is_identity():
    m = saturation_matrix(1.0)
    ident = identity_matrix()
    for a, b in zip(m, ident):
        assert abs(a - b) < 1e-6


def test_saturation_zero_grayscale_columns_equal():
    # En saturation 0, chaque canal de sortie reçoit la même combinaison luma
    m = saturation_matrix(0.0)
    # Première colonne (R out) doit égaler 2e (G out) et 3e (B out) pour les 3 premières rangées
    for row in range(3):
        r = m[row * 5 + 0]
        g = m[row * 5 + 1]
        b = m[row * 5 + 2]
        assert abs(r - g) < 1e-6
        assert abs(g - b) < 1e-6


def test_slider_mapping():
    assert slider_to_saturation(0) == 0.0
    assert slider_to_saturation(100) == 1.0
    assert slider_to_saturation(200) == 2.0


if __name__ == "__main__":
    test_identity_diagonal()
    test_saturation_one_is_identity()
    test_saturation_zero_grayscale_columns_equal()
    test_slider_mapping()
    print("OK")
