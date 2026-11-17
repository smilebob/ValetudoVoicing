"""YouTube audio extraction, trimming, and optional Demucs vocal isolation."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import httpx
import numpy as np
import soundfile as sf


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required system binary '{name}' was not found on PATH.")
    return path


def download_youtube_audio(
    url: str,
    work_dir: Path,
    start: str | None = None,
    end: str | None = None,
    isolate_vocals: bool = False,
    auto_trim: bool = False,
) -> tuple[Path, float]:
    """Download audio from a YouTube URL, trim, optionally isolate vocals, and normalize to 24kHz mono WAV.

    Returns (path_to_clean_wav, duration_seconds).
    """
    _require_binary("ffmpeg")

    raw_audio = work_dir / "raw_download.wav"
    # Use yt-dlp Python module or CLI to download best audio as WAV
    cmd_yt = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format",
        "wav",
        "-o",
        str(work_dir / "raw_download.%(ext)s"),
        url,
    ]
    subprocess.run(cmd_yt, check=True)

    if not raw_audio.exists():
        wavs = list(work_dir.glob("raw_download.*"))
        if not wavs:
            raise RuntimeError("yt-dlp did not produce an audio file.")
        raw_audio = wavs[0]

    trimmed_audio = work_dir / "trimmed.wav"
    cmd_trim = ["ffmpeg", "-y", "-i", str(raw_audio)]
    if start:
        cmd_trim.extend(["-ss", start])
    if end:
        cmd_trim.extend(["-to", end])
    cmd_trim.extend(["-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", str(trimmed_audio)])
    subprocess.run(cmd_trim, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    source_for_norm = trimmed_audio

    if isolate_vocals:
        source_for_norm = _isolate_vocals_demucs(trimmed_audio, work_dir)

    clean_wav = work_dir / "reference.wav"
    # Normalize loudness and convert to 24kHz mono PCM 16-bit for TTS reference
    cmd_norm = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_for_norm),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-af",
        "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-acodec",
        "pcm_s16le",
        str(clean_wav),
    ]
    subprocess.run(cmd_norm, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if auto_trim and not start and not end:
        auto_wav = work_dir / "reference_auto.wav"
        dur = extract_best_speech_segment(clean_wav, auto_wav)
        shutil.move(str(auto_wav), str(clean_wav))
        return clean_wav, dur

    info = sf.info(str(clean_wav))
    return clean_wav, float(info.duration)


def extract_best_speech_segment(
    wav_path: Path,
    output_wav: Path,
    target_min_sec: float = 12.0,
    target_max_sec: float = 25.0,
) -> float:
    """Detect active speech regions via RMS energy and extract the cleanest 12-25s window."""
    audio, sr = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    total_dur = len(audio) / sr
    if total_dur <= target_max_sec:
        sf.write(str(output_wav), audio, sr, subtype="PCM_16")
        return float(total_dur)

    frame_len = int(0.02 * sr)  # 20ms frames
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        sf.write(str(output_wav), audio, sr, subtype="PCM_16")
        return float(total_dur)

    frames = audio[: n_frames * frame_len].reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)

    noise_floor = float(np.percentile(rms, 20))
    peak_level = float(np.percentile(rms, 95))
    threshold = max(noise_floor * 2.5, peak_level * 0.15, 0.01)
    active = rms > threshold

    # Bridge short silences (< 0.4s = 20 frames)
    bridge_gap = 20
    segments: list[tuple[int, int]] = []
    in_seg = False
    seg_start = 0
    last_active = 0
    for i, is_act in enumerate(active):
        if is_act:
            if not in_seg:
                in_seg = True
                seg_start = i
            last_active = i
        elif in_seg and (i - last_active) > bridge_gap:
            segments.append((seg_start, last_active + 1))
            in_seg = False
    if in_seg:
        segments.append((seg_start, last_active + 1))

    # Filter out short blips (< 0.8s = 40 frames)
    min_frames = 40
    scored: list[tuple[float, int, int]] = []
    for s, e in segments:
        if (e - s) >= min_frames:
            seg_rms = float(np.mean(rms[s:e]))
            speech_ratio = float(np.mean(active[s:e]))
            score = seg_rms * speech_ratio * min((e - s) * 0.02, 20.0)
            scored.append((score, s, e))

    if not scored:
        # Fallback: take a 20s slice starting at 10% into the file
        start_idx = min(int(0.1 * len(audio)), max(0, len(audio) - int(target_max_sec * sr)))
        end_idx = min(len(audio), start_idx + int(target_max_sec * sr))
        clipped = audio[start_idx:end_idx]
        sf.write(str(output_wav), clipped, sr, subtype="PCM_16")
        return float(len(clipped) / sr)

    scored.sort(key=lambda x: x[0], reverse=True)
    pause_pad = np.zeros(int(0.15 * sr), dtype="float32")
    chunks: list[np.ndarray] = []
    accumulated_sec = 0.0

    for _, s, e in scored:
        start_sample = s * frame_len
        end_sample = min(len(audio), e * frame_len)
        seg_audio = audio[start_sample:end_sample]
        seg_dur = len(seg_audio) / sr

        if accumulated_sec + seg_dur > target_max_sec:
            remaining = target_max_sec - accumulated_sec
            if remaining >= 2.0:
                chunks.append(seg_audio[: int(remaining * sr)])
                accumulated_sec += remaining
            break

        chunks.append(seg_audio)
        chunks.append(pause_pad)
        accumulated_sec += seg_dur
        if accumulated_sec >= target_min_sec:
            break

    final_audio = np.concatenate(chunks) if chunks else audio[: int(target_max_sec * sr)]
    sf.write(str(output_wav), final_audio, sr, subtype="PCM_16")
    return float(len(final_audio) / sr)


def download_soundboard_clips(
    audio_urls: list[str],
    work_dir: Path,
    isolate_vocals: bool = False,
) -> tuple[Path, float]:
    """Download direct soundboard audio clips, concatenate them, and normalize to 24kHz mono WAV."""
    _require_binary("ffmpeg")
    clip_files: list[Path] = []

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for idx, url in enumerate(audio_urls):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                ext = ".wav" if url.lower().endswith(".wav") else ".mp3"
                raw_clip = work_dir / f"clip_{idx}{ext}"
                raw_clip.write_bytes(resp.content)

                norm_clip = work_dir / f"clip_{idx}_norm.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(raw_clip), "-ac", "1", "-ar", "24000", "-acodec", "pcm_s16le", str(norm_clip)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                clip_files.append(norm_clip)
            except Exception:
                continue

    if not clip_files:
        raise RuntimeError("Impossible de télécharger les extraits depuis le soundboard.")

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in clip_files), encoding="utf-8")

    merged_wav = work_dir / "merged.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(merged_wav)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    source_for_norm = _isolate_vocals_demucs(merged_wav, work_dir) if isolate_vocals else merged_wav
    clean_wav = work_dir / "reference.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(source_for_norm),
            "-ac", "1", "-ar", "24000",
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-acodec", "pcm_s16le", str(clean_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    final_wav = work_dir / "reference_auto.wav"
    dur = extract_best_speech_segment(clean_wav, final_wav)
    shutil.move(str(final_wav), str(clean_wav))
    return clean_wav, dur


def _isolate_vocals_demucs(audio_path: Path, work_dir: Path) -> Path:
    """Run Demucs two-stem vocal separation to remove background music."""
    try:
        import demucs.separate  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Vocal isolation requires 'demucs'. Install it with: uv sync --extra isolate"
        ) from exc

    demucs_out = work_dir / "demucs_out"
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "--two-stems=vocals",
        "-n",
        "htdemucs",
        "-o",
        str(demucs_out),
        str(audio_path),
    ]
    subprocess.run(cmd, check=True)

    vocals_candidates = list(demucs_out.rglob("vocals.wav"))
    if not vocals_candidates:
        raise RuntimeError("Demucs finished but vocals.wav was not found.")
    return vocals_candidates[0]


def extract_youtube_voice(
    url: str,
    start: str | None = None,
    end: str | None = None,
    isolate_vocals: bool = False,
    auto_trim: bool = False,
) -> tuple[tempfile.TemporaryDirectory, Path, float]:
    """Convenience wrapper that extracts into a TemporaryDirectory."""
    tmp = tempfile.TemporaryDirectory(prefix="valetudo_voicing_")
    wav_path, duration = download_youtube_audio(
        url=url,
        work_dir=Path(tmp.name),
        start=start,
        end=end,
        isolate_vocals=isolate_vocals,
        auto_trim=auto_trim,
    )
    return tmp, wav_path, duration


def extract_soundboard_voice(
    audio_urls: list[str],
    isolate_vocals: bool = False,
) -> tuple[tempfile.TemporaryDirectory, Path, float]:
    """Convenience wrapper that downloads and merges soundboard clips into a TemporaryDirectory."""
    tmp = tempfile.TemporaryDirectory(prefix="valetudo_voicing_")
    wav_path, duration = download_soundboard_clips(
        audio_urls=audio_urls,
        work_dir=Path(tmp.name),
        isolate_vocals=isolate_vocals,
    )
    return tmp, wav_path, duration
