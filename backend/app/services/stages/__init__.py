"""CutPilot AI — analysis stage modules.

Each module is a pure, testable function (no FastAPI, no DB).
They are orchestrated by ``app.services.analysis_pipeline.run_analysis``.
"""

from .transcribe import transcribe_audio
from .fillers import detect_fillers
from .silence import detect_silence
from .scenes import detect_scenes
from .vision import describe_frame, extract_frames, vision_available
from .diarization import diarize, assign_speakers_to_words, HEURISTIC_NOTE as DIARIZATION_HEURISTIC_NOTE
from .energy import compute_energy
from .hook import detect_hook
from .keywords import extract_keywords
from .audio_qc import check_audio_quality
from .summary import summarize
from .llm import LLMNotConfigured, chat as llm_chat, llm_available

__all__ = [
    "transcribe_audio",
    "detect_fillers",
    "detect_silence",
    "detect_scenes",
    "describe_frame",
    "extract_frames",
    "vision_available",
    "diarize",
    "assign_speakers_to_words",
    "DIARIZATION_HEURISTIC_NOTE",
    "compute_energy",
    "detect_hook",
    "extract_keywords",
    "check_audio_quality",
    "summarize",
    "LLMNotConfigured",
    "llm_chat",
    "llm_available",
]
