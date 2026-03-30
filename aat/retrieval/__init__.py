"""Retrieval module for academic translation.

Provides local library ingestion, OpenAlex retrieval, and grounding
for academic document translation.
"""

from aat.retrieval.cache import RetrievalCache, CacheEntry, CacheStats
from aat.retrieval.openalex import OpenAlexClient, OpenAlexResult
from aat.retrieval.ingestion import LibraryIngestion, ChunkMetadata
from aat.retrieval.grounding import (
    GroundingBuilder,
    TermBank,
    TermEntry,
    PhraseBank,
    PhraseEntry,
)

__all__ = [
    # Cache
    "RetrievalCache",
    "CacheEntry",
    "CacheStats",
    # OpenAlex
    "OpenAlexClient",
    "OpenAlexResult",
    # Ingestion
    "LibraryIngestion",
    "ChunkMetadata",
    # Grounding
    "GroundingBuilder",
    "TermBank",
    "TermEntry",
    "PhraseBank",
    "PhraseEntry",
]
