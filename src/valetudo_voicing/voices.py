"""Voice profile storage and management."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import yaml


def get_voices_dir() -> Path:
    """Return the root directory where learned voice profiles are stored."""
    env_home = os.environ.get("VALETUDO_VOICING_HOME")
    if env_home:
        base = Path(env_home)
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) / "valetudo-voicing" if xdg_data else Path.home() / ".local" / "share" / "valetudo-voicing"
    voices_dir = base / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    return voices_dir


@dataclass
class VoiceProfile:
    """Metadata and reference audio path for a learned voice."""

    name: str
    reference_wav: Path
    source_url: str
    source_lang: str
    created_at: str
    isolated_vocals: bool
    duration_sec: float


def save_voice_profile(
    name: str,
    reference_wav: Path,
    source_url: str,
    source_lang: str,
    isolated_vocals: bool,
    duration_sec: float,
) -> VoiceProfile:
    """Persist a learned voice profile and its reference WAV."""
    safe_name = name.strip()
    if not safe_name or "/" in safe_name or "\\" in safe_name:
        raise ValueError(f"Invalid voice profile name: {name!r}")

    profile_dir = get_voices_dir() / safe_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    target_wav = profile_dir / "reference.wav"
    shutil.copy2(reference_wav, target_wav)

    created_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "name": safe_name,
        "source_url": source_url,
        "source_lang": source_lang,
        "created_at": created_at,
        "isolated_vocals": isolated_vocals,
        "duration_sec": round(duration_sec, 2),
    }
    with (profile_dir / "profile.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)

    return VoiceProfile(
        name=safe_name,
        reference_wav=target_wav,
        source_url=source_url,
        source_lang=source_lang,
        created_at=created_at,
        isolated_vocals=isolated_vocals,
        duration_sec=round(duration_sec, 2),
    )


def load_voice_profile(name: str) -> VoiceProfile:
    """Load an existing voice profile by name."""
    profile_dir = get_voices_dir() / name
    meta_path = profile_dir / "profile.yaml"
    wav_path = profile_dir / "reference.wav"
    if not meta_path.exists() or not wav_path.exists():
        raise FileNotFoundError(f"Voice profile '{name}' not found in {get_voices_dir()}")

    with meta_path.open("r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    return VoiceProfile(
        name=meta["name"],
        reference_wav=wav_path,
        source_url=meta.get("source_url", ""),
        source_lang=meta.get("source_lang", "auto"),
        created_at=meta.get("created_at", ""),
        isolated_vocals=bool(meta.get("isolated_vocals", False)),
        duration_sec=float(meta.get("duration_sec", 0.0)),
    )


def list_voice_profiles() -> list[VoiceProfile]:
    """Return all saved voice profiles sorted by name."""
    profiles: list[VoiceProfile] = []
    for entry in sorted(get_voices_dir().iterdir()):
        if entry.is_dir() and (entry / "profile.yaml").exists():
            try:
                profiles.append(load_voice_profile(entry.name))
            except Exception:
                continue
    return profiles


def delete_voice_profile(name: str) -> None:
    """Delete a saved voice profile."""
    profile_dir = get_voices_dir() / name
    if not profile_dir.exists():
        raise FileNotFoundError(f"Voice profile '{name}' not found")
    shutil.rmtree(profile_dir)
