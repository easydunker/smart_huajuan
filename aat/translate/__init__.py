"""Translation module."""

# Use absolute imports to avoid circular initialization issues
from aat.parsing.citation import CitationExtractor
from aat.parsing.docx_parser import DocxParser
from aat.translate.llm_client import create_client
from aat.translate.pipeline import TranslationPipeline, PipelineError
from aat.translate.segmenter import Segmenter
from aat.translate.validators import (
    run_all_validators,
)
from aat.translate.prompts import (
    DraftTranslationPrompt,
    CriticReviewPrompt,
    RevisionPrompt,
)
from aat.storage.checkpoints import CheckpointManager
from aat.storage.models import TranslationProject
from aat.translate.translation_memory import TranslationMemory

__all__ = [
    "citation",
    "docx_parser",
    "llm_client",
    "pipeline",
    "segmenter",
    "validators",
    "prompts",
    "translation_memory",
]
