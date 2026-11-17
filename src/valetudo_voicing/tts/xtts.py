"""Coqui XTTS-v2 local CPU voice-cloning backend."""

import os
from pathlib import Path
from .base import TTSBackend

XTTS_SUPPORTED_LANGS = {
    "en", "es", "fr", "de", "it", "pt", "pl", "tr",
    "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja", "hi",
}


class XTTSBackend(TTSBackend):
    """Coqui XTTS-v2 multilingual zero-shot voice cloning on CPU."""

    name = "xtts"

    def __init__(self) -> None:
        self._tts = None

    def load(self) -> None:
        if self._tts is not None:
            return
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        from TTS.api import TTS  # type: ignore

        self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)

    def synthesize(
        self,
        text: str,
        speaker_wav: Path,
        language: str,
        output_wav: Path,
    ) -> None:
        if self._tts is None:
            self.load()

        lang = language.lower()
        if lang == "zh":
            lang = "zh-cn"
        if lang not in XTTS_SUPPORTED_LANGS:
            raise ValueError(
                f"Language '{language}' is not supported by XTTS-v2. "
                f"Supported: {', '.join(sorted(XTTS_SUPPORTED_LANGS))}"
            )

        output_wav.parent.mkdir(parents=True, exist_ok=True)
        self._tts.tts_to_file(
            text=text,
            speaker_wav=str(speaker_wav),
            language=lang,
            file_path=str(output_wav),
        )
