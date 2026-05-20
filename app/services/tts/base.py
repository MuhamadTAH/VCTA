from abc import ABC, abstractmethod
from typing import Optional


class BaseTTSProvider(ABC):
    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_reference: Optional[dict] = None,
    ) -> str:
        """
        Generate audio from text.
        Args:
            text: The text to synthesize
            output_path: Path to save the generated audio file
            voice_reference: Optional dict with voice metadata (name, language, audio_url)
        Returns:
            Path to the generated audio file
        """
        ...