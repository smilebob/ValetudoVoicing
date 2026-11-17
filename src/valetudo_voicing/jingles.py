"""Synthetic intro/outro jingles (Star Trek, R2-D2, Gong, Chime, Portal) for Roborock S5 WAVs."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class JingleSpec:
    """Definition of a synthetic jingle preset."""

    id: str
    name: str
    description: str


JINGLES: list[JingleSpec] = [
    JingleSpec("none", "Aucun jingle", "Pas de bruitage d'intro"),
    JingleSpec("startrek", "Communicateur Star Trek", "Double bip futuriste de communicateur"),
    JingleSpec("r2d2", "Bip R2-D2", "Petit gazouillis rapide d'astromech"),
    JingleSpec("gong", "Gong zen", "Résonance grave et apaisante"),
    JingleSpec("chime", "Carillon doux", "Accord ascendant cristallin"),
    JingleSpec("portal", "Bip Aperture (Portal)", "Bip clinique de laboratoire"),
]

JINGLE_MAP: dict[str, JingleSpec] = {j.id: j for j in JINGLES}


def _synth_tone(freq_start: float, freq_end: float, dur_sec: float, sr: int = 16000, amp: float = 0.35) -> np.ndarray:
    n = max(1, int(dur_sec * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    freqs = np.linspace(freq_start, freq_end, n, dtype=np.float32)
    phase = 2.0 * np.pi * np.cumsum(freqs) / float(sr)
    wave = np.sin(phase)
    fade = min(n // 4, int(0.015 * sr))
    env = np.ones(n, dtype=np.float32)
    if fade > 0:
        env[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        env[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return (wave * env * amp).astype(np.float32)


def generate_jingle_audio(jingle_id: str, sr: int = 16000) -> np.ndarray:
    """Synthesize a short jingle waveform at `sr` Hz."""
    jid = jingle_id.strip().lower()
    if jid not in JINGLE_MAP:
        raise ValueError(f"Jingle inconnu '{jingle_id}'. Disponibles : {', '.join(JINGLE_MAP.keys())}")
    if jid == "none":
        return np.zeros(0, dtype=np.float32)

    gap = np.zeros(int(0.04 * sr), dtype=np.float32)
    if jid == "startrek":
        return np.concatenate([_synth_tone(987.77, 987.77, 0.09, sr), gap, _synth_tone(1318.51, 1318.51, 0.14, sr)])
    if jid == "r2d2":
        return np.concatenate([
            _synth_tone(784.0, 1318.0, 0.07, sr),
            _synth_tone(1568.0, 988.0, 0.08, sr),
            _synth_tone(1046.5, 1760.0, 0.09, sr),
        ])
    if jid == "gong":
        n = int(0.65 * sr)
        t = np.arange(n, dtype=np.float32) / float(sr)
        decay = np.exp(-4.5 * t)
        wave = (np.sin(2 * np.pi * 164.81 * t) + 0.5 * np.sin(2 * np.pi * 247.2 * t)) * decay * 0.4
        return wave.astype(np.float32)
    if jid == "chime":
        return np.concatenate([
            _synth_tone(523.25, 523.25, 0.10, sr, 0.28),
            _synth_tone(659.25, 659.25, 0.10, sr, 0.28),
            _synth_tone(783.99, 783.99, 0.18, sr, 0.32),
        ])
    # portal
    return np.concatenate([_synth_tone(1200.0, 1200.0, 0.06, sr, 0.3), gap, _synth_tone(800.0, 800.0, 0.08, sr, 0.28)])


def apply_jingle(wav_path: Path, jingle_id: str, output_wav: Path | None = None) -> Path:
    """Prepend a synthetic jingle + 120ms pause before `wav_path`."""
    jid = jingle_id.strip().lower()
    target = output_wav if output_wav else wav_path
    if jid == "none":
        if target != wav_path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav_path, target)
        return target

    audio, sr = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    jingle = generate_jingle_audio(jid, sr=sr)
    pause = np.zeros(int(0.12 * sr), dtype=np.float32)
    combined = np.concatenate([jingle, pause, audio.astype(np.float32)])

    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target), combined, sr, subtype="PCM_16")
    return target
