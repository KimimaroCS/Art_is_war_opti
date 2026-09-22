# DebunkPC — Saturation écran

Outil Python **Windows** pour régler la saturation / Digital Vibrance **par écran**, **compatible plein écran exclusif** (via le pilote GPU).

## Compatible jeux (exclusif)

| Backend | Quand | Plein écran exclusif |
|---|---|---|
| **NVIDIA Digital Vibrance** (NVAPI) | GPU NVIDIA | ✅ Oui |
| **AMD Saturation** (ADL) | GPU AMD | ✅ Oui |
| Windows Magnifier (secours) | Intel / pas d’API GPU | ❌ Non → borderless |

L’outil choisit automatiquement **NVIDIA → AMD → Magnifier**.

## Prérequis

- Windows 10 / 11
- Python 3.10+ (tkinter inclus)
- Pilote NVIDIA ou AMD à jour
- **Aucune dépendance pip**

## Lancer

```bat
cd screen-saturation
python main.py
```

ou `run.bat`

## Utilisation

1. Vérifie le badge vert : `✓ NVIDIA Digital Vibrance — plein écran exclusif OK`
2. Choisis l’écran du jeu
3. Monte la saturation (> 100 %)
4. Lance ton jeu en **plein écran exclusif** — l’effet reste

**Réinitialiser** restaure le niveau d’origine (celui d’avant l’outil).

## Multi-écrans

- Un seul écran : le jeu plus saturé, Discord/OBS intacts
- Case « tous les écrans » : applique à chaque sortie GPU détectée

## Structure

```
screen-saturation/
  main.py
  saturation/
    app.py
    engine.py              # choisit le backend
    monitors.py
    matrix.py
    backends/
      nvidia.py            # Digital Vibrance (exclusif OK)
      amd.py               # ADL saturation (exclusif OK)
      magnification.py     # secours OS
```

## Limites

- Écran branché sur iGPU Intel → souvent Magnifier seulement
- Sur laptop NVIDIA Optimus : l’écran doit être piloté par le GPU NVIDIA pour NVAPI
- Fermer l’app restaure les valeurs d’origine
