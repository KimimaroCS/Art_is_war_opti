"""Matrices de couleur 5x5 pour l'API Magnification Windows."""

from __future__ import annotations

# Poids de luminance Rec.601 (standard pour effets de saturation type GDI+)
_LUMA_R = 0.3086
_LUMA_G = 0.6094
_LUMA_B = 0.0820


def identity_matrix() -> list[float]:
    """Matrice identité (aucun effet), rangée par rangée (25 floats)."""
    return [
        1.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 1.0,
    ]


def saturation_matrix(saturation: float) -> list[float]:
    """Construit une matrice de saturation.

    Args:
        saturation: 0.0 = niveaux de gris, 1.0 = normal, >1.0 = plus saturé.
                    Plage recommandée UI : 0.0 → 2.0.
    """
    s = float(saturation)
    r, g, b = _LUMA_R, _LUMA_G, _LUMA_B
    inv = 1.0 - s

    # Colonnes = sortie R,G,B,A,T — rangées = entrée R,G,B,A,1
    return [
        inv * r + s, inv * r,     inv * r,     0.0, 0.0,
        inv * g,     inv * g + s, inv * g,     0.0, 0.0,
        inv * b,     inv * b,     inv * b + s, 0.0, 0.0,
        0.0,         0.0,         0.0,         1.0, 0.0,
        0.0,         0.0,         0.0,         0.0, 1.0,
    ]


def slider_to_saturation(percent: float) -> float:
    """Convertit un slider 0–200 (%) en facteur de saturation.

    100 = normal (1.0), 0 = gris, 200 = saturation x2.
    """
    return max(0.0, float(percent)) / 100.0
