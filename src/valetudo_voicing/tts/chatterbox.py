"""Chatterbox Multilingual optional local CPU voice-cloning backend."""

from pathlib import Path
from .base import TTSBackend

CHATTERBOX_SUPPORTED_LANGS = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
}


class ChatterboxBackend(TTSBackend):
    """Resemble AI Chatterbox Multilingual voice cloning on CPU."""

    name = "chatterbox"

    def __init__(self) -> None:
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Chatterbox backend requires 'chatterbox-tts'. Install it with: uv sync --extra chatterbox"
            ) from exc
        self._model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")

    def synthesize(
        self,
        text: str,
        speaker_wav: Path,
        language: str,
        output_wav: Path,
    ) -> None:
        if self._model is None:
            self.load()

        import torchaudio as ta  # type: ignore

        lang = language.lower()
        if lang == "zh-cn":
            lang = "zh"
        if lang not in CHATTERBOX_SUPPORTED_LANGS:
            raise ValueError(
                f"Language '{language}' is not supported by Chatterbox Multilingual. "
                f"Supported: {', '.join(sorted(CHATTERBOX_SUPPORTED_LANGS))}"
            )

        output_wav.parent.mkdir(parents=True, exist_ok=True)
        wav = self._model.generate(text, audio_prompt_path=str(speaker_wav), language_id=lang)
        ta.save(str(output_wav), wav, self._model.sr)
