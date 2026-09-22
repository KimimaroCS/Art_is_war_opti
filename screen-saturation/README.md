# DebunkPC — Saturation écran

Outil Python **Windows** pour augmenter / diminuer la **saturation** des couleurs sur **un écran au choix** (multi-moniteurs supporté).

Idéal pour rendre un jeu plus “vibrant” pendant tes TikToks DebunkPC, sans toucher aux autres écrans (Discord, OBS, etc.).

## Prérequis

- Windows 10 / 11
- Python 3.10+
- Carte graphique compatible WDDM (standard aujourd’hui)
- **Aucune dépendance pip** (stdlib + ctypes + tkinter)

> Tkinter est inclus avec l’installateur Python officiel Windows.  
> Si `tkinter` manque : réinstalle Python en cochant **tcl/tk**.

## Lancer

```bat
cd screen-saturation
python main.py
```

## Utilisation

1. Choisis l’**écran cible** dans la liste
2. Règle la **saturation** (100 % = normal, >100 % = plus saturé)
3. Clique **Appliquer**
4. **Réinitialiser** pour tout remettre à zéro

Option **Appliquer à tous les écrans** : utilise l’effet fullscreen Magnification (global).

## Jeux

| Mode d’affichage | Résultat typique |
|---|---|
| Fenêtré / Borderless | ✅ Filtre OK |
| Plein écran exclusif | ⚠️ Parfois ignoré par le jeu |

Pour Fortnite / Valorant / etc. : passe en **borderless** si le filtre ne s’applique pas.

## Comment ça marche

- **Un écran** : fenêtre Magnifier invisible sur le moniteur choisi + matrice de saturation (`MagSetColorEffect`)
- **Tous les écrans** : `MagSetFullscreenColorEffect`
- Les clics passent à travers (la souris reste utilisable sur le jeu)

## Structure

```
screen-saturation/
  main.py
  saturation/
    app.py        # UI
    engine.py     # Magnification API
    monitors.py   # Détection multi-écrans
    matrix.py     # Matrice de saturation
```

## Limites

- Windows uniquement
- Ce n’est **pas** le Digital Vibrance NVIDIA / Saturation AMD (niveau GPU) : c’est un filtre OS. Pour un réglage permanent GPU, utilise le panneau NVIDIA/AMD.
- Fermer l’app retire l’effet
