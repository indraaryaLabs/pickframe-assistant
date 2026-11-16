"""A grounded support assistant for PickFrame, plus the harness that measures it."""

from pickframe_assistant.assistant import Assistant, AssistantConfig
from pickframe_assistant.knowledge import Corpus, load_corpus
from pickframe_assistant.model import Answer, Citation, Kind, Language

__all__ = [
    "Answer",
    "Assistant",
    "AssistantConfig",
    "Citation",
    "Corpus",
    "Kind",
    "Language",
    "load_corpus",
]

__version__ = "1.0.0"
