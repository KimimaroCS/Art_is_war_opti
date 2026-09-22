"""Courbes de grading « naturelles » — meilleures que le Digital Vibrance seul.

Idée : au lieu de sur-saturer (effet plastique), on applique une courbe S
(contraste dans les tons moyens) + une vibrance très légère optionnelle.
Les couleurs paraissent plus riches sans peaux criardes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GradeParams:
    """Paramètres 0.0–1.0 (sauf vibrance_boost mappé ailleurs)."""

    presence: float = 0.35  # force de la courbe S (0 = neutre, 1 = fort)
    shadow_lift: float = 0.08  # remonte un peu les noirs (lisibilité jeu)
    highlight_roll: float = 0.12  # adoucit les hautes lumières
    vibrance: float = 0.15  # 0–1 → sera mappé vers DVC autour du défaut
    gamma: float = 1.0  # 1.0 neutre ; <1 plus clair, >1 plus sombre


# Presets joueur — vibrance volontairement basse
PRESETS: dict[str, GradeParams] = {
    "Off": GradeParams(presence=0.0, shadow_lift=0.0, highlight_roll=0.0, vibrance=0.0, gamma=1.0),
    "Naturel": GradeParams(presence=0.32, shadow_lift=0.06, highlight_roll=0.10, vibrance=0.12, gamma=0.98),
    "Cinématique": GradeParams(presence=0.45, shadow_lift=0.04, highlight_roll=0.18, vibrance=0.08, gamma=1.05),
    "Compétitif": GradeParams(presence=0.28, shadow_lift=0.14, highlight_roll=0.06, vibrance=0.10, gamma=0.94),
    "Punch": GradeParams(presence=0.55, shadow_lift=0.05, highlight_roll=0.12, vibrance=0.22, gamma=0.97),
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _s_curve(x: float, amount: float) -> float:
    """Courbe S douce centrée sur 0.5. amount 0→identité, 1→contraste marqué."""
    if amount <= 1e-6:
        return x
    # Contraste autour des tons moyens + smoothstep pour éviter le clipping dur
    c = 1.0 + amount * 1.7
    y = 0.5 + (x - 0.5) * c
    y = _clamp(y)
    # Légère polarisation smoothstep pour un rendu plus « film »
    t = _clamp(y)
    smooth = t * t * (3.0 - 2.0 * t)
    return _clamp(y * (1.0 - amount * 0.25) + smooth * (amount * 0.25))


def _apply_grade_sample(x: float, p: GradeParams) -> float:
    """Transforme un échantillon linéaire 0–1."""
    y = _clamp(x)
    # Shadow lift (additif soft)
    if p.shadow_lift > 0:
        lift = p.shadow_lift * (1.0 - y) * (1.0 - y)
        y = _clamp(y + lift)
    # Presence S-curve
    y = _s_curve(y, _clamp(p.presence))
    # Highlight rolloff
    if p.highlight_roll > 0 and y > 0.7:
        t = (y - 0.7) / 0.3
        y = y - t * t * p.highlight_roll * 0.25
        y = _clamp(y)
    # Gamma
    g = p.gamma if p.gamma > 0.01 else 1.0
    y = _clamp(y ** (1.0 / g))
    return y


def build_gamma_lut_1024(params: GradeParams) -> list[tuple[float, float, float]]:
    """LUT 1024 entrées (R,G,B) en float 0–1 pour NVAPI SetTargetGammaCorrection."""
    out: list[tuple[float, float, float]] = []
    for i in range(1024):
        x = i / 1023.0
        v = _apply_grade_sample(x, params)
        out.append((v, v, v))
    return out


def build_win_gamma_ramp(params: GradeParams) -> tuple[list[int], list[int], list[int]]:
    """Rampes Windows 256 × WORD (0–65535), bits de poids fort utilisés."""
    r: list[int] = []
    g: list[int] = []
    b: list[int] = []
    for i in range(256):
        x = i / 255.0
        v = _apply_grade_sample(x, params)
        word = int(round(v * 65535.0))
        word = 0 if word < 0 else 65535 if word > 65535 else word
        r.append(word)
        g.append(word)
        b.append(word)
    return r, g, b


def vibrance_to_saturation_factor(vibrance: float) -> float:
    """Mappe vibrance UI 0–1 vers facteur saturation outil (1.0 = défaut driver).

    On reste volontairement proche de 1.0 : 0→0.85, 0.5→1.0, 1→1.25
    (évite l'effet plastique du DVC à fond).
    """
    v = _clamp(float(vibrance))
    if v <= 0.5:
        return 0.85 + (1.0 - 0.85) * (v / 0.5)
    return 1.0 + (1.25 - 1.0) * ((v - 0.5) / 0.5)
