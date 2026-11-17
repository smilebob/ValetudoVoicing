# ValetudoVoicing

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg)](pyproject.toml)
[![CI](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml/badge.svg)](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml)
[![Valetudo](https://img.shields.io/badge/Valetudo-Roborock-00B4D8.svg)](https://valetudo.cloud/)

**[🇬🇧 English](README.md)** | **🇫🇷 Français**

> **Donnez à votre robot aspirateur Roborock sous Valetudo n'importe quelle voix — 100% en local sur CPU.**
> Clonez une voix depuis YouTube (dans n'importe quelle langue) ou enregistrez votre propre voix au microphone, appliquez **23+ effets vocaux amusants** (Dark Vador, C-3PO, R2-D2, GLaDOS, Dalek, Kylo Ren, Minion, Daft Punk...) et **6 jingles synthétiques**, préécoutez avant de générer, et déployez directement sur votre robot via le réseau local.

---

## Fonctionnalités principales

- **Clonage vocal 100% local (CPU)** — Basé sur **Coqui XTTS-v2** (17 langues) avec option **Chatterbox Multilingual** (23 langues). Aucune clé API ni GPU requis.
- **Recherche automatique de personnage** — Indiquez un nom et une langue (`--character "GLaDOS" --lang fr`) : l'outil cherche sur YouTube et les soundboards publics, extrait automatiquement le meilleur passage vocal et peut isoler la voix de la musique via **Demucs** (`--isolate-vocals`).
- **Dictée interactive au microphone** — Enregistrez votre propre pack de base phrase par phrase avec barre de progression, suppression automatique des silences et réécoute immédiate.
- **Packs de base réutilisables** — Vos enregistrements propres sont conservés dans `./recordings/<nom>/` pour générer à volonté de nouveaux `.pkg` avec différents effets et jingles sans jamais tout réenregistrer.
- **23 effets vocaux + 6 jingles synthétiques** — Avec pré-écoute en direct avant l'empaquetage (`preview-effect` ou touche `p` dans la TUI).
- **Interface globale `ncurses` + CLI complète** — Tout le workflow au clavier (`valetudo-voicing tui`) ou en ligne de commande (`--ui-lang fr|en`).
- **Tous les Roborock supportés par Valetudo** — Profils dédiés pour **V1, S4, S4 Max, S5, S5 Max, S6 / S6 Pure, S6 MaxV, S7 / S7+, S7 MaxV / S7 Pro Ultra et Q7 Max / Q7 Max+** (incluant serpillière/réservoir d'eau et station d'auto-vidage), **détection automatique via l'API Valetudo** (`/api/v2/robot`), export WAV/OGG (`--format wav|ogg`), expansion des alias firmware (`start_clean.wav`, `stop_clean.wav`, `back_dock.wav`, `spot_clean.wav`, etc.), chiffrement `.pkg` via `ccrypt` (`r0ckrobo#23456`) et déploiement direct via `VoicePackManagementCapability`.

---

## Modèles Roborock supportés

| ID Robot (`--robot`) | Modèle | Jeux de sons inclus |
| --- | --- | --- |
| `roborock_v1` | Xiaomi Mi Robot Vacuum (V1) | `base` |
| `roborock_s4` | Roborock S4 | `base` |
| `roborock_s4max` | Roborock S4 Max | `base` |
| `roborock_s5` | Roborock S5 | `base` |
| `roborock_s5max` | Roborock S5 Max | `base`, `mop` |
| `roborock_s6` | Roborock S6 / S6 Pure | `base`, `mop` |
| `roborock_s6maxv` | Roborock S6 MaxV | `base`, `mop` |
| `roborock_s7` | Roborock S7 / S7+ | `base`, `mop`, `autodock` |
| `roborock_s7pro` | Roborock S7 MaxV / S7 Pro Ultra | `base`, `mop`, `autodock` |
| `roborock_q7max` | Roborock Q7 Max / Q7 Max+ | `base`, `mop`, `autodock` |

Lancez `uv run valetudo-voicing robots` ou passez `--robot-ip <ip>` à `init` pour détecter automatiquement votre modèle via Valetudo.

---

## Prérequis système

- **Python 3.11 ou 3.12** (géré automatiquement par [`uv`](https://docs.astral.sh/uv/))
- **`ffmpeg`** et **`ccrypt`** :
  ```bash
  sudo apt install ffmpeg ccrypt
  ```
- *(Optionnel pour la dictée/écoute sous Linux)* : `alsa-utils` (`arecord`) et `pipewire-bin` (`pw-play`) ou `ffplay`.

---

## Installation

```bash
git clone https://github.com/smilebob/ValetudoVoicing.git
cd ValetudoVoicing

# Installation de base (Coqui XTTS-v2 sur CPU + yt-dlp + TUI ncurses)
uv sync

# Optionnel : séparation vocale Demucs (--isolate-vocals)
uv sync --extra isolate

# Optionnel : moteur Chatterbox Multilingual (--backend chatterbox)
uv sync --extra chatterbox
```

---

## Utilisation rapide

### Option 1 : Interface globale `ncurses` (Recommandé)

```bash
uv run valetudo-voicing tui
# ou :
uv run valetudo-voicing-tui
```

La TUI vous guide à travers les 7 étapes (avec sélecteur de langue FR/EN) :
1. **Apprendre une voix** (par nom de personnage ou URL YouTube)
2. **Gérer les profils vocaux enregistrés** (écouter, sélectionner, supprimer)
3. **Créer / Éditer le script YAML et les textes** (choix ou auto-détection du modèle Roborock, filtres par catégorie)
4. **Générer le `.pkg` par synthèse vocale (TTS)**
5. **Dicter le `.pkg` avec ma propre voix** (microphone + barre de progression)
6. **Appliquer effet/jingle sur un pack de base existant** (avec pré-écoute en direct !)
7. **Déployer le `.pkg` sur le Roborock** via Valetudo

### Option 2 : Ligne de commande (CLI)

```bash
# 1. Apprendre une voix par nom de personnage (ou URL YouTube)
uv run valetudo-voicing learn --character "GLaDOS" --lang fr --name glados --isolate-vocals

# 2. Créer le script YAML pour votre modèle Roborock (ou détection auto via --robot-ip)
uv run valetudo-voicing robots
uv run valetudo-voicing init mon_pack.yaml --name mon_glados --robot roborock_s7 --lang fr --interactive

# 3. Synthétiser et générer mon_glados.pkg (avec effet, jingle et format wav|ogg optionnels)
uv run valetudo-voicing generate mon_pack.yaml --voice glados --effect glados --jingle portal --format wav

# OU : Dicter votre propre pack de base (sauvegardé proprement dans ./recordings/mon_glados/)
uv run valetudo-voicing record mon_pack.yaml

# 4. Préécouter puis appliquer un autre effet sans réenregistrer
uv run valetudo-voicing preview-effect vador --base mon_glados --jingle startrek
uv run valetudo-voicing apply-effect mon_glados --effect vador --jingle startrek

# 5. Déployer directement sur le Roborock sous Valetudo
uv run valetudo-voicing deploy mon_glados_vador.pkg --robot-ip 192.168.1.50 --lang fr
```

*(Passez `--ui-lang fr` ou `--ui-lang en` avant n'importe quelle commande pour forcer la langue de l'interface.)*

---

## Référence des commandes CLI

| Commande | Description |
| --- | --- |
| `tui` | Lancer l'interface globale `ncurses` |
| `robots` | Lister tous les modèles Roborock supportés et leurs capacités |
| `learn` | Apprendre une voix depuis une recherche de personnage ou une URL YouTube |
| `voices` / `delete-voice` | Lister ou supprimer les profils vocaux enregistrés |
| `init` / `edit` | Générer ou éditer interactivement le script YAML du voicepack |
| `generate` | Synthétiser tous les sons actifs (ou `--only <fichier>`) via TTS et créer le `.pkg` |
| `record` | Dicter interactivement sa propre voix au microphone avec barre de progression |
| `apply-effect` | Appliquer un effet/jingle sur un pack de base existant dans `./recordings/` |
| `preview-effect` | Préécouter un effet/jingle sur un profil vocal, un pack de base ou un WAV |
| `effects` / `jingles` | Lister les 23 effets vocaux et les 6 jingles synthétiques |
| `deploy` | Servir le `.pkg` via HTTP temporaire et l'envoyer à Valetudo (`VoicePackManagementCapability`) |

---

## Effets vocaux (23) & Jingles (6) disponibles

| Catégorie | IDs d'effets (`--effect`) |
| --- | --- |
| **Sci-Fi & Robots** | `vador` (Dark Vador), `c3po` (C-3PO), `r2d2` (synthé astromech R2-D2), `glados` (GLaDOS), `dalek` (modulation 30 Hz), `kylo` (Kylo Ren), `daftpunk` (Vocoder), `robot`, `alien` |
| **Voix & Personnages** | `helium`, `ogre`, `minion`, `yoda`, `ghost`, `whisper` |
| **Rétro & Ambiances** | `radio` (Talkie-walkie NASA), `megaphone`, `vintage` (Téléphone années 30), `8bit`, `underwater`, `cathedral`, `stadium`, `none` |

**Jingles (`--jingle`)** : `none`, `startrek`, `r2d2`, `gong`, `chime`, `portal`.

---

## Contribution & Licence

Les contributions, signalements de bugs et nouvelles idées d'effets sont les bienvenus ! Voir [CONTRIBUTING.md](CONTRIBUTING.md).
Distribué sous licence **Apache License 2.0** — voir [LICENSE](LICENSE).
