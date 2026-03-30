"""Local library ingestion for academic documents.

Provides PDF and DOCX text extraction, chunking, and embedding storage
for local library management.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChunkMetadata:
    """Metadata for a document chunk."""

    source_path: str
    chunk_id: str
    chunk_index: int
    total_chunks: int
    language: str  # "zh" or "en" or "unknown"
    source_type: str = "local_library"
    file_hash: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source_path": self.source_path,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "language": self.language,
            "source_type": self.source_type,
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMetadata":
        """Create from dictionary."""
        return cls(
            source_path=data["source_path"],
            chunk_id=data["chunk_id"],
            chunk_index=data["chunk_index"],
            total_chunks=data["total_chunks"],
            language=data["language"],
            source_type=data.get("source_type", "local_library"),
            file_hash=data.get("file_hash", ""),
        )


class LibraryIngestion:
    """Ingest local library documents (PDF, DOCX) into vector store.

    Provides:
    - Text extraction from PDF and DOCX files
    - Chunking to ~300 tokens per chunk
    - Language detection (zh/en)
    - Incremental ingestion (skip unchanged files)
    """

    CHUNK_SIZE_TOKENS = 300
    # Approximate chars per token (conservative)
    CHARS_PER_TOKEN = 4
    CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN

    def __init__(
        self,
        vector_store_dir: Path,
        embedding_model: str = "bge-m3",
    ) -> None:
        """
        Initialize library ingestion.

        Args:
            vector_store_dir: Directory for vector store.
            embedding_model: Name of embedding model to use.
        """
        self.vector_store_dir = Path(vector_store_dir)
        self.vector_store_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model

        # Simple JSON-based storage for now
        self.chunks_file = self.vector_store_dir / "chunks.json"
        self.metadata_file = self.vector_store_dir / "metadata.json"
        self._load_data()

    def _load_data(self) -> None:
        """Load existing data from disk."""
        import json

        if self.chunks_file.exists():
            try:
                with open(self.chunks_file, "r", encoding="utf-8") as f:
                    self._chunks = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._chunks = {}
        else:
            self._chunks = {}

        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._metadata = {}
        else:
            self._metadata = {}

    def _save_data(self) -> None:
        """Save data to disk."""
        import json

        with open(self.chunks_file, "w", encoding="utf-8") as f:
            json.dump(self._chunks, f, ensure_ascii=False, indent=2)

        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash of file content for change detection."""
        import hashlib

        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _detect_language(self, text: str) -> str:
        """Detect if text is Chinese or English."""
        # Simple heuristic: check for Chinese characters
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        total_chars = len(text.strip())

        if total_chars == 0:
            return "unknown"

        chinese_ratio = chinese_chars / total_chars

        if chinese_ratio > 0.1:  # More than 10% Chinese characters
            return "zh"
        else:
            return "en"

    def _extract_text_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        try:
            import PyPDF2
        except ImportError:
            raise RuntimeError("PyPDF2 is required for PDF extraction. Install with: pip install PyPDF2")

        text_parts = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n".join(text_parts)

    def _extract_text_from_docx(self, file_path: Path) -> str:
        """Extract text from DOCX file."""
        try:
            import docx
        except ImportError:
            raise RuntimeError("python-docx is required for DOCX extraction. Install with: pip install python-docx")

        doc = docx.Document(file_path)
        text_parts = []

        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)

        return "\n".join(text_parts)

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks of approximately CHUNK_SIZE_CHARS."""
        if not text:
            return []

        chunks = []
        current_chunk = []
        current_length = 0

        # Split on paragraphs first
        paragraphs = text.split("\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_length = len(para)

            if current_length + para_length > self.CHUNK_SIZE_CHARS and current_chunk:
                # Save current chunk
                chunks.append("\n".join(current_chunk))
                current_chunk = [para]
                current_length = para_length
            else:
                current_chunk.append(para)
                current_length += para_length

        # Don't forget the last chunk
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def ingest_file(self, file_path: Path) -> dict:
        """Ingest a single file into the library.

        Args:
            file_path: Path to PDF or DOCX file.

        Returns:
            Dict with ingestion results including chunk count.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Compute file hash for change detection
        file_hash = self._compute_file_hash(file_path)

        # Check if file already ingested and unchanged
        file_id = str(file_path.resolve())
        if file_id in self._metadata:
            if self._metadata[file_id].get("file_hash") == file_hash:
                return {
                    "file_path": str(file_path),
                    "status": "unchanged",
                    "chunks_added": 0,
                }

        # Extract text based on file type
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            text = self._extract_text_from_pdf(file_path)
        elif suffix == ".docx":
            text = self._extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Detect language
        language = self._detect_language(text)

        # Chunk text
        chunks = self._chunk_text(text)

        # Store chunks with metadata
        chunk_ids = []
        for i, chunk_text in enumerate(chunks):
            chunk_id = f"{file_hash}_{i}"
            chunk_ids.append(chunk_id)

            metadata = ChunkMetadata(
                source_path=str(file_path),
                chunk_id=chunk_id,
                chunk_index=i,
                total_chunks=len(chunks),
                language=language,
                source_type="local_library",
                file_hash=file_hash,
            )

            self._chunks[chunk_id] = {
                "text": chunk_text,
                "metadata": metadata.to_dict(),
            }

        # Update file metadata
        self._metadata[file_id] = {
            "file_path": str(file_path),
            "file_hash": file_hash,
            "chunk_count": len(chunks),
            "chunk_ids": chunk_ids,
            "language": language,
        }

        # Save to disk
        self._save_data()

        return {
            "file_path": str(file_path),
            "status": "ingested",
            "chunks_added": len(chunks),
            "language": language,
        }

    def get_chunks(self, chunk_ids: list[str] | None = None) -> list[dict]:
        """Get chunks by IDs, or all chunks if no IDs provided.

        Args:
            chunk_ids: Optional list of chunk IDs to retrieve.

        Returns:
            List of chunk dictionaries with text and metadata.
        """
        if chunk_ids is None:
            return list(self._chunks.values())

        result = []
        for chunk_id in chunk_ids:
            if chunk_id in self._chunks:
                result.append(self._chunks[chunk_id])
        return result

    def search_by_language(self, language: str) -> list[dict]:
        """Get all chunks of a specific language.

        Args:
            language: Language code ("zh", "en", etc.).

        Returns:
            List of chunk dictionaries.
        """
        result = []
        for chunk_id, chunk_data in self._chunks.items():
            metadata = chunk_data.get("metadata", {})
            if metadata.get("language") == language:
                result.append(chunk_data)
        return result

    def get_stats(self) -> dict:
        """Get ingestion statistics.

        Returns:
            Dictionary with stats about ingested files and chunks.
        """
        total_chunks = len(self._chunks)
        total_files = len(self._metadata)

        languages = {}
        for file_id, file_meta in self._metadata.items():
            lang = file_meta.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1

        return {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "languages": languages,
        }
