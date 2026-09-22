# DebunkPC Color — grading naturel (mieux que Digital Vibrance)

Outil Windows pour un rendu **plus beau que le Digital Vibrance NVIDIA** :
on priorise des **courbes gamma (présence)** et on garde la vibrance **légère**.

Compatible **plein écran exclusif** (LUT pipeline NVIDIA).

## Pourquoi pas « juste » Digital Vibrance ?

Le DVC NVIDIA sature tout uniformément → peaux roses, ciel criard, look plastique.
**DebunkPC Color** fait l’inverse de la mode TikTok « vibrance 100 % » :

1. **Présence** — courbe S (contraste tons moyens)
2. **Lift ombres** — lisibilité en jeu
3. **Vibrance légère** — appoint seulement
4. **Gamma** — équilibre global

## Backend

| Priorité | Backend | Exclusif |
|---|---|---|
| 1 | **DebunkPC Natural (NVIDIA)** — LUT `SetTargetGammaCorrection` + DVC soft | ✅ |
| 2 | AMD ADL saturation | ✅ |
| 3 | Magnifier (secours) | ❌ |

## Lancer

```bat
cd screen-saturation
python main.py
```

## Presets

| Preset | Usage |
|---|---|
| **Naturel** | Recommandé au quotidien / TikTok |
| Cinématique | Plus contrasté, vibrance encore plus basse |
| Compétitif | Ombres relevées (visibilité) |
| Punch | Plus agressif |
| Off | Neutre |

Sélectionne **uniquement l’écran du jeu** pour laisser Discord/OBS intacts.

## Limites

- NVIDIA recommandé pour le vrai grading LUT
- Sur Optimus : l’écran doit être piloté par le GPU NVIDIA
- Réinitialiser / fermer l’app restaure l’état d’origine
