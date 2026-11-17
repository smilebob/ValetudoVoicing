# ValetudoVoicing

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg)](pyproject.toml)
[![CI](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml/badge.svg)](https://github.com/smilebob/ValetudoVoicing/actions/workflows/ci.yml)
[![Valetudo](https://img.shields.io/badge/Valetudo-Roborock%20S5-00B4D8.svg)](https://valetudo.cloud/)

**🇬🇧 English** | **[🇫🇷 Français](README.fr.md)**

> **Give your Roborock S5 running Valetudo any voice in the world — 100% locally on CPU.**
> Clone a character voice from YouTube (any language), or record your own voice interactively via microphone, apply **23+ fun audio effects** (Darth Vader, C-3PO, R2-D2, GLaDOS, Dalek, Kylo Ren, Minion, Daft Punk...) and **6 synthetic jingles**, preview before building, and deploy directly to your vacuum over your LAN.

---

## Key Features

- **100% Local & Private Voice Cloning (CPU)** — Powered by **Coqui XTTS-v2** (17 languages) with optional **Chatterbox Multilingual** backend (23 languages). No cloud API keys or GPU required.
- **Automatic Character Voice Discovery** — Give a character name + language (`--character "GLaDOS" --lang en`) and `ValetudoVoicing` searches YouTube + public soundboards, extracts the cleanest speech segment automatically, and optionally isolates vocals from background music with **Demucs**.
- **Interactive Microphone Dictation** — Record your own personal base voice pack phrase-by-phrase with a live progress bar, automatic silence trimming, and instant playback.
- **Reusable Base Packs** — Keep your clean personal recordings in `./recordings/<pack_name>/` and generate unlimited `.pkg` variants with different effects & jingles in seconds — no re-recording needed.
- **23 Fun Voice Effects + 6 Synthetic Jingles** — Real-time preview before packaging (`preview-effect` or `p` in TUI).
- **Full-Screen `ncurses` TUI + Scriptable CLI** — Complete end-to-end workflow in a keyboard-driven terminal UI (`valetudo-voicing tui`) or modular CLI commands (`--ui-lang en|fr`).
- **Complete Roborock S5 Compatibility** — Normalizes audio to 16 kHz mono 16-bit PCM WAV, expands firmware aliases (`start_clean.wav`, `stop_clean.wav`, `back_dock.wav`, `spot_clean.wav`, etc.), encrypts `.pkg` with `ccrypt` (`r0ckrobo#23456`), and deploys directly via Valetudo's `VoicePackManagementCapability` API.

---

## Prerequisites

- **Python 3.11 or 3.12** (managed automatically by [`uv`](https://docs.astral.sh/uv/))
- **`ffmpeg`** (audio conversion, trimming, and effects)
- **`ccrypt`** (Roborock S5 `.pkg` encryption):
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

The TUI walks you through all 7 steps:
1. **Learn a voice** (by character name or YouTube URL)
2. **Manage saved voice profiles** (listen, select, delete)
3. **Create / Edit YAML script & phrases** (45 Roborock S5 prompts, category filters)
4. **Generate `.pkg` via TTS voice cloning**
5. **Record `.pkg` with your own voice** (microphone + progress bar)
6. **Apply effect / jingle to an existing base pack** (with live audio preview!)
7. **Deploy `.pkg` directly to your Roborock S5** via Valetudo

### Option 2: Command-Line Interface (CLI)

```bash
# 1. Learn a voice automatically by character name (or pass a YouTube URL)
uv run valetudo-voicing learn --character "GLaDOS" --lang en --name glados --isolate-vocals

# 2. Generate a customizable YAML script (English or French)
uv run valetudo-voicing init my_pack.yaml --name my_glados --lang en --interactive

# 3. Synthesize & package into my_glados.pkg (with optional effect & jingle)
uv run valetudo-voicing generate my_pack.yaml --voice glados --effect glados --jingle portal

# OR: Record your own voice interactively (saved cleanly in ./recordings/my_glados/)
uv run valetudo-voicing record my_pack.yaml

# 4. Preview & apply new effects to your base pack without re-recording
uv run valetudo-voicing preview-effect vador --base my_glados --jingle startrek
uv run valetudo-voicing apply-effect my_glados --effect vador --jingle startrek

# 5. Deploy directly to your Roborock S5 running Valetudo
uv run valetudo-voicing deploy my_glados_vador.pkg --robot-ip 192.168.1.50 --lang en
```

*(Pass `--ui-lang fr` or `--ui-lang en` before any command to force the interface language.)*

---

## Available Voice Effects (23) & Jingles (6)

| Category | Effect IDs (`--effect`) |
| --- | --- |
| **Sci-Fi & Robots** | `vador` (Darth Vader), `c3po` (C-3PO), `r2d2` (R2-D2 astromech synth), `glados` (GLaDOS), `dalek` (30 Hz ring mod), `kylo` (Kylo Ren), `daftpunk` (Vocoder), `robot`, `alien` |
| **Pitch & Characters** | `helium`, `ogre`, `minion`, `yoda`, `ghost`, `whisper` |
| **Retro & Environments** | `radio` (NASA walkie-talkie), `megaphone`, `vintage` (1930s phone), `8bit`, `underwater`, `cathedral`, `stadium`, `none` |

**Jingles (`--jingle`)**: `none`, `startrek`, `r2d2`, `gong`, `chime`, `portal`.

Run `uv run valetudo-voicing effects` or `uv run valetudo-voicing jingles` to see full descriptions.

---

## Contributing & License

Contributions, bug reports, and new sound/effect ideas are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).
