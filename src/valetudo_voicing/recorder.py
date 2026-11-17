"""Interactive microphone recording and playback helpers for custom voice dictation."""

from pathlib import Path
import shutil
import signal
import subprocess
import time


def record_until_enter(output_wav: Path, device: str = "default", sample_rate: int = 24000) -> float:
    """Record audio from the microphone via `arecord` until the user presses Enter.

    Returns the recording duration in seconds.
    """
    arecord = shutil.which("arecord")
    if not arecord:
        raise RuntimeError(
            "Le binaire 'arecord' (alsa-utils) est requis pour enregistrer au microphone."
        )

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        arecord,
        "-D",
        device,
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        "1",
        "-t",
        "wav",
        "-q",
        str(output_wav),
    ]
    start_time = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        input()
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    return max(0.0, time.monotonic() - start_time)


def trim_and_normalize_recording(src_wav: Path, dst_wav: Path) -> None:
    """Trim leading/trailing silence and normalize a mic recording for Roborock S5 (16kHz mono PCM)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to process recorded audio.")

    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src_wav),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        (
            "highpass=f=80,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-40dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-40dB,"
            "areverse,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        ),
        "-acodec",
        "pcm_s16le",
        str(dst_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play_wav(wav_path: Path) -> bool:
    """Play a WAV file using pw-play, paplay, ffplay, or aplay. Returns True if playback succeeded."""
    candidates: list[list[str]] = []
    if pw_play := shutil.which("pw-play"):
        candidates.append([pw_play, str(wav_path)])
    if paplay := shutil.which("paplay"):
        candidates.append([paplay, str(wav_path)])
    if ffplay := shutil.which("ffplay"):
        candidates.append([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav_path)])
    if aplay := shutil.which("aplay"):
        candidates.append([aplay, "-q", str(wav_path)])

    for cmd in candidates:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if res.returncode == 0:
            return True

    return False
