"""Fun voice effects (Darth Vader, C-3PO, R2-D2, GLaDOS, Dalek, etc.) for Roborock S5 WAVs."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np
from scipy.signal import butter, sosfilt
import soundfile as sf


@dataclass(frozen=True)
class VoiceEffect:
    """Definition of a voice effect preset."""

    id: str
    name: str
    description: str


VOICE_EFFECTS: list[VoiceEffect] = [
    VoiceEffect("none", "Aucun (naturel)", "Voix originale sans modification"),
    VoiceEffect("vador", "Dark Vador", "Voix grave, sombre et résonance métallique de masque"),
    VoiceEffect("c3po", "C-3PO", "Voix aiguë, nasillarde et métallique de droïde protocolaire"),
    VoiceEffect("r2d2", "R2-D2", "Traduit la parole en bips et sifflements de droïde astromech"),
    VoiceEffect("glados", "GLaDOS (Portal)", "Voix synthétique froide avec chorus robotique"),
    VoiceEffect("dalek", "Dalek (Doctor Who)", "Modulation en anneau 30 Hz agressive et robotique"),
    VoiceEffect("robot", "Robot classique", "Effet flanger et résonance métallique courte"),
    VoiceEffect("helium", "Hélium / Écureuil", "Voix très aiguë et accélérée"),
    VoiceEffect("ogre", "Ogre / Géant", "Voix très grave et caverneuse"),
    VoiceEffect("radio", "Talkie-walkie / NASA", "Son filtré radio basse-fidélité"),
    VoiceEffect("megaphone", "Mégaphone / Gare", "Annonce saturée avec écho de hall"),
    VoiceEffect("ghost", "Fantôme / Spectral", "Trémolo inquiétant et réverbération"),
    VoiceEffect("8bit", "Rétro 8-bit", "Voix pixelisée style console rétro"),
    VoiceEffect("cathedral", "Cathédrale / Épique", "Grande réverbération majestueuse"),
    VoiceEffect("kylo", "Kylo Ren", "Voix grave, rauque et saturée de casque"),
    VoiceEffect("yoda", "Yoda / Lutin", "Voix perchée, nasale avec léger phaser"),
    VoiceEffect("minion", "Minion", "Voix très aiguë, rapide et espiègle"),
    VoiceEffect("alien", "Alien / Extraterrestre", "Modulation spatiale et flanger cosmique"),
    VoiceEffect("daftpunk", "Daft Punk / Vocoder", "Voix robotique harmonisée multi-voix"),
    VoiceEffect("vintage", "Téléphone années 30", "Bande étroite rétro avec saturation vintage"),
    VoiceEffect("underwater", "Sous l'eau", "Voix étouffée aquatique avec modulation lente"),
    VoiceEffect("whisper", "Chuchotement / ASMR", "Voix soufflée haute fréquence inquiétante"),
    VoiceEffect("stadium", "Annonceur de stade", "Écho de stade géant et compresseur"),
]

EFFECT_MAP: dict[str, VoiceEffect] = {e.id: e for e in VOICE_EFFECTS}

_FFMPEG_FILTERS: dict[str, str] = {
    "vador": "asetrate=16000*0.76,aresample=16000,atempo=1.315,aecho=0.8:0.7:18:0.4,equalizer=f=120:t=q:w=1:g=6,lowpass=f=3200",
    "c3po": "asetrate=16000*1.12,aresample=16000,atempo=0.893,highpass=f=420,lowpass=f=4500,aecho=0.8:0.88:12:0.35,chorus=0.5:0.9:25:0.4:0.25:2",
    "glados": "chorus=0.6:0.9:30|40:0.4|0.3:0.25|0.3:2|1.5,aecho=0.8:0.85:15:0.25,highpass=f=220",
    "robot": "flanger=delay=5:depth=4:regen=50:width=80:speed=2,aecho=0.8:0.8:14:0.4",
    "helium": "asetrate=16000*1.45,aresample=16000,atempo=0.69",
    "ogre": "asetrate=16000*0.65,aresample=16000,atempo=1.538,aecho=0.8:0.85:45:0.45",
    "radio": "highpass=f=500,lowpass=f=2400,acrusher=bits=8:mode=log",
    "megaphone": "highpass=f=400,lowpass=f=3200,aecho=0.8:0.8:120|220:0.4|0.25",
    "ghost": "tremolo=f=7:d=0.75,aecho=0.8:0.9:60|120:0.5|0.35",
    "8bit": "acrusher=bits=5:samples=4:mode=lin",
    "cathedral": "aecho=0.8:0.9:90|180|270:0.5|0.35|0.2",
    "kylo": "asetrate=16000*0.72,aresample=16000,atempo=1.38,acrusher=bits=7:mode=log,aecho=0.8:0.75:22:0.45,lowpass=f=2800",
    "yoda": "asetrate=16000*1.22,aresample=16000,atempo=0.82,aphaser=in_gain=0.4:out_gain=0.74:delay=3.0:decay=0.4:speed=0.5,highpass=f=350",
    "minion": "asetrate=16000*1.55,aresample=16000,atempo=0.72,vibrato=f=6:d=0.35",
    "alien": "flanger=delay=8:depth=6:regen=65:width=90:speed=4,aphaser=type=t:speed=1.5,aecho=0.8:0.85:35:0.4",
    "vintage": "highpass=f=600,lowpass=f=2100,acrusher=bits=7:mode=log,aecho=0.8:0.7:10:0.2",
    "underwater": "lowpass=f=550,vibrato=f=3.5:d=0.65,aecho=0.8:0.85:40:0.45",
    "whisper": "highpass=f=1200,chorus=0.5:0.9:25:0.4:0.25:2,aecho=0.8:0.85:50:0.35",
    "stadium": "highpass=f=250,aecho=0.8:0.88:110|230|360:0.55|0.35|0.2",
}


def _apply_dalek(audio: np.ndarray, sr: int) -> np.ndarray:
    """Apply 30 Hz ring modulation + light overdrive."""
    t = np.arange(len(audio), dtype=np.float32) / float(sr)
    carrier = np.sin(2.0 * np.pi * 30.0 * t)
    modulated = audio * carrier
    driven = np.tanh(modulated * 3.0) * 0.85
    return driven.astype(np.float32)


def _apply_vocoder(audio: np.ndarray, sr: int) -> np.ndarray:
    """16-band channel vocoder with sawtooth chord carrier (classic Daft Punk effect)."""
    if len(audio) == 0:
        return audio

    t = np.arange(len(audio), dtype=np.float32) / float(sr)
    # Rich sawtooth chord carrier (C3 + G3 + C4 + E4)
    carrier = np.zeros_like(audio, dtype=np.float32)
    for freq in (130.81, 196.00, 261.63, 329.63):
        phase = (t * freq) % 1.0
        carrier += (2.0 * phase - 1.0)
    carrier /= 4.0

    nyq = 0.5 * sr
    edges = np.geomspace(180.0, min(6800.0, nyq * 0.9), 17)
    env_sos = butter(2, min(40.0 / nyq, 0.9), btype="low", output="sos")

    vocoded = np.zeros_like(audio, dtype=np.float32)
    for i in range(16):
        lo = edges[i] / nyq
        hi = min(edges[i + 1] / nyq, 0.98)
        if lo >= hi:
            continue
        bp_sos = butter(2, [lo, hi], btype="band", output="sos")
        mod_band = sosfilt(bp_sos, audio)
        car_band = sosfilt(bp_sos, carrier)
        env = np.maximum(0.0, sosfilt(env_sos, np.abs(mod_band)))
        vocoded += car_band * env * 6.0

    # Add subtle high-passed consonants (> 2.5 kHz) for crisp speech intelligibility
    hp_sos = butter(2, min(2500.0 / nyq, 0.9), btype="high", output="sos")
    consonants = sosfilt(hp_sos, audio) * 0.22
    out = vocoded * 0.88 + consonants

    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = out / max(peak, 1.0) * 0.9
    return out.astype(np.float32)


def _apply_r2d2(audio: np.ndarray, sr: int) -> np.ndarray:
    """Convert speech envelope into playful R2-D2 style astromech beeps and chirps."""
    if len(audio) == 0:
        return audio

    frame_len = max(1, int(0.08 * sr))  # 80ms syllables
    n_frames = max(1, len(audio) // frame_len)
    rng = np.random.default_rng(abs(int(np.sum(np.abs(audio[:1000])) * 10000)) % (2**31))

    out = np.zeros_like(audio, dtype=np.float32)
    pentatonic = np.array([523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1174.66, 1318.51, 1567.98])

    for i in range(n_frames):
        s = i * frame_len
        e = min(len(audio), s + frame_len)
        seg = audio[s:e]
        rms = float(np.sqrt(np.mean(seg**2)))
        if rms < 0.015:
            continue

        dur_samples = e - s
        t = np.arange(dur_samples, dtype=np.float32) / float(sr)
        f_start = float(rng.choice(pentatonic))
        # Alternate between steady warble and quick chirp/glissando
        if rng.random() < 0.65:
            f_end = float(rng.choice(pentatonic)) * rng.uniform(0.85, 1.35)
        else:
            f_end = f_start

        freq_curve = np.linspace(f_start, f_end, dur_samples, dtype=np.float32)
        phase = 2.0 * np.pi * np.cumsum(freq_curve) / float(sr)
        vibrato = 0.25 * np.sin(2.0 * np.pi * 35.0 * t)
        beep = np.sin(phase + vibrato) + 0.25 * np.sin(2.0 * phase)

        # Smooth ADSR envelope
        env = np.ones(dur_samples, dtype=np.float32)
        fade = min(dur_samples // 4, int(0.01 * sr))
        if fade > 0:
            env[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            env[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)

        amp = min(0.8, max(0.25, rms * 2.5))
        out[s:e] = (beep * env * amp).astype(np.float32)

    return out


def apply_voice_effect(wav_path: Path, effect_id: str, output_wav: Path | None = None) -> Path:
    """Apply a named voice effect to `wav_path`, keeping Roborock S5 16kHz mono PCM format."""
    norm_id = effect_id.strip().lower()
    if norm_id not in EFFECT_MAP:
        raise ValueError(
            f"Effet inconnu '{effect_id}'. Disponibles : {', '.join(EFFECT_MAP.keys())}"
        )

    target = output_wav if output_wav else wav_path
    if norm_id == "none":
        if target != wav_path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav_path, target)
        return target

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg est requis pour appliquer les effets vocaux.")

    with tempfile.TemporaryDirectory(prefix="valetudo_fx_") as tmp_dir:
        tmp_out = Path(tmp_dir) / "fx.wav"

        if norm_id in ("dalek", "r2d2", "daftpunk"):
            audio, sr = sf.read(str(wav_path), dtype="float32")
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            if norm_id == "dalek":
                processed = _apply_dalek(audio, sr)
            elif norm_id == "r2d2":
                processed = _apply_r2d2(audio, sr)
            else:
                processed = _apply_vocoder(audio, sr)
            raw_fx = Path(tmp_dir) / "raw_fx.wav"
            sf.write(str(raw_fx), processed, sr, subtype="PCM_16")
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(raw_fx),
                    "-ac", "1", "-ar", "16000",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-acodec", "pcm_s16le", str(tmp_out),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            filter_chain = _FFMPEG_FILTERS[norm_id] + ",loudnorm=I=-16:TP=-1.5:LRA=11"
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(wav_path),
                    "-ac", "1", "-ar", "16000",
                    "-af", filter_chain,
                    "-acodec", "pcm_s16le", str(tmp_out),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), str(target))

    return target
