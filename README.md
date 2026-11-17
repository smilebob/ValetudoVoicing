# ValetudoVoicing

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg)](pyproject.toml)
[![CI](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml/badge.svg)](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml)
[![Valetudo](https://img.shields.io/badge/Valetudo-Roborock-00B4D8.svg)](https://valetudo.cloud/)

**🇬🇧 English** | **[🇫🇷 Français](README.fr.md)**

> **Give your Roborock vacuum running Valetudo any voice in the world — 100% locally on CPU.**
> Clone a character voice from YouTube (any language), or record your own voice interactively via microphone, apply **23+ fun audio effects** (Darth Vader, C-3PO, R2-D2, GLaDOS, Dalek, Kylo Ren, Minion, Daft Punk...) and **6 synthetic jingles**, preview before building, and deploy directly to your vacuum over your LAN.

---

## Key Features

- **100% Local & Private Voice Cloning (CPU)** — Powered by **Coqui XTTS-v2** (17 languages) with optional **Chatterbox Multilingual** backend (23 languages). No cloud API keys or GPU required.
- **Automatic Character Voice Discovery** — Give a character name + language (`--character "GLaDOS" --lang en`) and `ValetudoVoicing` searches YouTube + public soundboards, extracts the cleanest speech segment automatically, and optionally isolates vocals from background music with **Demucs**.
- **Interactive Microphone Dictation** — Record your own personal base voice pack phrase-by-phrase with a live progress bar, automatic silence trimming, and instant playback.
- **Reusable Base Packs** — Keep your clean personal recordings in `./recordings/<pack_name>/` and generate unlimited `.pkg` variants with different effects & jingles in seconds — no re-recording needed.
- **23 Fun Voice Effects + 6 Synthetic Jingles** — Real-time audio preview before packaging (`preview-effect` or `p` in TUI).
- **Full-Screen `ncurses` TUI + Scriptable CLI** — Complete end-to-end workflow in a keyboard-driven terminal UI (`valetudo-voicing tui`) or modular CLI commands (`--ui-lang en|fr`).
- **All Valetudo-Supported Roborock Models** — Dedicated profiles for **V1, S4, S4 Max, S5, S5 Max, S6 / S6 Pure, S6 MaxV, S7 / S7+, S7 MaxV / S7 Pro Ultra, and Q7 Max / Q7 Max+** (including mop/water-tank and auto-empty dock prompts), with **auto-detection via Valetudo API** (`/api/v2/robot`), WAV/OGG packaging (`--format wav|ogg`), firmware alias expansion (`start_clean.wav`, `stop_clean.wav`, `back_dock.wav`, `spot_clean.wav`, etc.), `ccrypt` `.pkg` encryption (`r0ckrobo#23456`), and direct LAN deployment.

---

## Supported Roborock Models

| Robot ID (`--robot`) | Model | Included Prompt Sets |
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

Run `uv run valetudo-voicing robots` or pass `--robot-ip <ip>` to `init` to auto-detect your vacuum model from Valetudo.

---

## Prerequisites

- **Python 3.11 or 3.12** (managed automatically by [`uv`](https://docs.astral.sh/uv/))
- **`ffmpeg`** (audio conversion, trimming, OGG encoding, and effects)
- **`ccrypt`** (Roborock `.pkg` encryption):
  ```bash
  sudo apt install ffmpeg ccrypt
  ```
- *(Optional, for microphone recording/playback on Linux)*: `alsa-utils` (`arecord`) and `pipewire-bin` (`pw-play`) or `ffplay`.

---

## Installation

```bash
git clone https://github.com/smilebob/ValetudoVoicing.git
cd ValetudoVoicing

# Base installation (Coqui XTTS-v2 on CPU + yt-dlp + ncurses TUI)
uv sync

# Optional: Demucs vocal isolation (--isolate-vocals)
uv sync --extra isolate

# Optional: Chatterbox Multilingual TTS backend (--backend chatterbox)
uv sync --extra chatterbox
```

---

## Quick Start

### Option 1: Full-Screen `ncurses` TUI (Recommended)

```bash
uv run valetudo-voicing tui
# or:
uv run valetudo-voicing-tui
```

The TUI walks you through all 7 steps (plus an EN/FR language switcher):
1. **Learn a voice** (by character name or YouTube URL)
2. **Manage saved voice profiles** (listen, select, delete)
3. **Create / Edit YAML script & phrases** (pick or auto-detect Roborock model, category filters)
4. **Generate `.pkg` via TTS voice cloning**
5. **Record `.pkg` with your own voice** (microphone + live progress bar)
6. **Apply effect / jingle to an existing base pack** (with live audio preview!)
7. **Deploy `.pkg` directly to your Roborock** via Valetudo

### Option 2: Command-Line Interface (CLI)

```bash
# 1. Learn a voice automatically by character name (or pass a YouTube URL)
uv run valetudo-voicing learn --character "GLaDOS" --lang en --name glados --isolate-vocals

# 2. Generate a customizable YAML script for your Roborock model (or auto-detect via --robot-ip)
uv run valetudo-voicing robots
uv run valetudo-voicing init my_pack.yaml --name my_glados --robot roborock_s7 --lang en --interactive

# 3. Synthesize & package into my_glados.pkg (with optional effect, jingle, and format wav|ogg)
uv run valetudo-voicing generate my_pack.yaml --voice glados --effect glados --jingle portal --format wav

# OR: Record your own voice interactively (saved cleanly in ./recordings/my_glados/)
uv run valetudo-voicing record my_pack.yaml

# 4. Preview & apply new effects to your base pack without re-recording
uv run valetudo-voicing preview-effect vador --base my_glados --jingle startrek
uv run valetudo-voicing apply-effect my_glados --effect vador --jingle startrek

# 5. Deploy directly to your Roborock running Valetudo
uv run valetudo-voicing deploy my_glados_vador.pkg --robot-ip 192.168.1.50 --lang en
```

*(Pass `--ui-lang fr` or `--ui-lang en` before any command to force the interface language.)*

---

## CLI Command Reference

| Command | Description |
| --- | --- |
| `tui` | Launch the full-screen `ncurses` TUI |
| `robots` | List all supported Roborock models and their capabilities |
| `learn` | Clone/save a voice profile from a character search or YouTube URL |
| `voices` / `delete-voice` | List or delete saved voice profiles |
| `init` / `edit` | Generate or interactively edit a voicepack YAML script |
| `generate` | Synthesize all enabled prompts (or `--only <file>`) via TTS and build `.pkg` |
| `record` | Interactively record your own voice via microphone with progress bar |
| `apply-effect` | Apply an effect/jingle to an existing base pack in `./recordings/` |
| `preview-effect` | Audio preview of any effect/jingle on a voice profile, base pack, or WAV |
| `effects` / `jingles` | List all 23 voice effects and 6 synthetic jingles |
| `deploy` | Serve `.pkg` over temporary HTTP and push to Valetudo (`VoicePackManagementCapability`) |

---

## Available Voice Effects (23) & Jingles (6)

| Category | Effect IDs (`--effect`) |
| --- | --- |
| **Sci-Fi & Robots** | `vador` (Darth Vader), `c3po` (C-3PO), `r2d2` (R2-D2 astromech synth), `glados` (GLaDOS), `dalek` (30 Hz ring mod), `kylo` (Kylo Ren), `daftpunk` (Vocoder), `robot`, `alien` |
| **Pitch & Characters** | `helium`, `ogre`, `minion`, `yoda`, `ghost`, `whisper` |
| **Retro & Environments** | `radio` (NASA walkie-talkie), `megaphone`, `vintage` (1930s phone), `8bit`, `underwater`, `cathedral`, `stadium`, `none` |

**Jingles (`--jingle`)**: `none`, `startrek`, `r2d2`, `gong`, `chime`, `portal`.

---

## Contributing & License

Contributions, bug reports, and new sound/effect ideas are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).
