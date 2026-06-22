from __future__ import annotations

from pathlib import Path
from typing import Protocol


class LocalTranscriptionWorker(Protocol):
    """Future seam for whisper.cpp-backed local transcription."""

    def transcribe(self, media_path: Path) -> str:
        raise NotImplementedError
