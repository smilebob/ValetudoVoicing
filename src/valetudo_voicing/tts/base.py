"""Abstract base class for local voice-cloning TTS backends."""

from abc import ABC, abstractmethod
from pathlib import Path


class TTSBackend(ABC):
    """Interface for local multilingual voice-cloning TTS engines."""

    name: str

    @abstractmethod
    def load(self) -> None:
        """Load the model into memory (CPU)."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        speaker_wav: Path,
        language: str,
        output_wav: Path,
    ) -> None:
        """Synthesize `text` in `language` using `speaker_wav` and write to `output_wav`."""
