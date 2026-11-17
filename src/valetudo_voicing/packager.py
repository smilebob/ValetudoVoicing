"""Audio normalization and Roborock S5 .pkg packaging (tar.gz + ccrypt)."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from .sounds import SOUND_ALIASES

ROBOROCK_CCRYPT_KEY = "r0ckrobo#23456"


def normalize_wav_for_roborock(src_wav: Path, dst_wav: Path) -> None:
    """Convert a synthesized WAV to Roborock S5 compatible format (16kHz, mono, 16-bit PCM)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to normalize WAV files.")

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
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-acodec",
        "pcm_s16le",
        str(dst_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def compute_md5(file_path: Path) -> str:
    """Return the lowercase hexadecimal MD5 digest of a file."""
    h = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_pkg(wav_dir: Path, output_pkg: Path, encrypt: bool = True) -> tuple[Path, str]:
    """Package all .wav files in `wav_dir` into a Roborock S5 .pkg file.

    Returns (output_pkg_path, md5_hex).
    """
    wav_files = sorted(wav_dir.glob("*.wav"))
    if not wav_files:
        raise ValueError(f"No .wav files found in {wav_dir}")

    output_pkg.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="valetudo_pkg_") as tmp_dir:
        tar_path = Path(tmp_dir) / "voicepack.tar.gz"
        existing_names = {w.name for w in wav_files}
        with tarfile.open(tar_path, "w:gz") as tar:
            for wav in wav_files:
                tar.add(wav, arcname=wav.name)
                for alias in SOUND_ALIASES.get(wav.name, ()):
                    if alias not in existing_names:
                        tar.add(wav, arcname=alias)
                        existing_names.add(alias)

        if encrypt:
            ccrypt = shutil.which("ccrypt")
            if not ccrypt:
                raise RuntimeError(
                    "'ccrypt' binary is required to encrypt Roborock S5 .pkg files.\n"
                    "Install it with: sudo apt install ccrypt  (or pass --no-encrypt for raw .tar.gz)"
                )
            subprocess.run(
                [ccrypt, "-e", "-f", "-K", ROBOROCK_CCRYPT_KEY, str(tar_path)],
                check=True,
            )
            encrypted_path = Path(f"{tar_path}.cpt")
            shutil.move(str(encrypted_path), str(output_pkg))
        else:
            shutil.move(str(tar_path), str(output_pkg))

    return output_pkg, compute_md5(output_pkg)
