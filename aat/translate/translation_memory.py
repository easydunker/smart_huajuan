"""Translation Memory (TM) for storing and retrieving translations."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from pathlib import Path
from datetime import datetime


if TYPE_CHECKING:
    pass


@dataclass
class TMEntry:
    """Entry in Translation Memory."""

    source_phrase: str
    normalized_key: str
    target_phrase: str
    first_used_chapter: str | None = None
    locked: bool = False
    confidence: float = 1.0
    created_at: datetime | None = None


@dataclass
class TranslationMemory:
    """Persistent Translation Memory store."""

    project_id: str
    entries: list[TMEntry] = field(default_factory=list)

    def add_entry(self, entry: TMEntry) -> None:
        """Add an entry to translation memory."""
        self.entries.append(entry)

    def find_entry(self, normalized_key: str) -> TMEntry | None:
        """Find entry by normalized key."""
        for entry in reversed(self.entries):  # Most recent first
            if entry.normalized_key == normalized_key:
                return entry
        return None

    def find_entries_by_chapter(self, chapter_id: str) -> list[TMEntry]:
        """Find all entries from a specific chapter."""
        return [e for e in self.entries if e.first_used_chapter == chapter_id]

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "project_id": self.project_id,
            "entries": [
                {
                    "source_phrase": e.source_phrase,
                    "normalized_key": e.normalized_key,
                    "target_phrase": e.target_phrase,
                    "first_used_chapter": e.first_used_chapter,
                    "locked": e.locked,
                    "confidence": e.confidence,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TranslationMemory":
        """Create from dict."""
        entries = []
        for entry_data in data.get("entries", []):
            entries.append(TMEntry(
                source_phrase=entry_data["source_phrase"],
                normalized_key=entry_data["normalized_key"],
                target_phrase=entry_data["target_phrase"],
                first_used_chapter=entry_data.get("first_used_chapter"),
                locked=entry_data.get("locked", False),
                confidence=entry_data.get("confidence", 1.0),
                created_at=datetime.fromisoformat(entry_data["created_at"]) if entry_data.get("created_at") else None,
            ))
        return cls(project_id=data["project_id"], entries=entries)

    def lock_term(self, normalized_key: str, target_phrase: str | None = None) -> bool:
        """
        Lock a term in the translation memory.

        Args:
            normalized_key: The normalized key of the term to lock.
            target_phrase: Optional target phrase to use if term doesn't exist.

        Returns:
            True if term was locked, False otherwise.
        """
        entry = self.find_entry(normalized_key)
        if entry:
            entry.locked = True
            if target_phrase:
                entry.target_phrase = target_phrase
            return True
        elif target_phrase:
            # Create new locked entry
            self.add_entry(TMEntry(
                source_phrase=normalized_key,
                normalized_key=normalized_key,
                target_phrase=target_phrase,
                locked=True,
                confidence=1.0,
                created_at=datetime.now(),
            ))
            return True
        return False

    def unlock_term(self, normalized_key: str) -> bool:
        """
        Unlock a term in the translation memory.

        Args:
            normalized_key: The normalized key of the term to unlock.

        Returns:
            True if term was unlocked, False if not found.
        """
        entry = self.find_entry(normalized_key)
        if entry:
            entry.locked = False
            return True
        return False

    def is_locked(self, normalized_key: str) -> bool:
        """
        Check if a term is locked.

        Args:
            normalized_key: The normalized key to check.

        Returns:
            True if term exists and is locked, False otherwise.
        """
        entry = self.find_entry(normalized_key)
        return entry.locked if entry else False

    def get_locked_terms(self) -> list[TMEntry]:
        """
        Get all locked terms in the translation memory.

        Returns:
            List of locked TMEntry objects.
        """
        return [entry for entry in self.entries if entry.locked]

    def enforce_locked_terms(self, text: str) -> str:
        """
        Enforce locked terms in a translated text.

        Replaces any occurrences of locked source terms with their
        locked target translations.

        Args:
            text: The translated text to enforce locked terms in.

        Returns:
            Text with locked terms enforced.
        """
        result = text
        for entry in self.get_locked_terms():
            # Simple string replacement - could be enhanced with word boundary detection
            if entry.source_phrase in result:
                result = result.replace(entry.source_phrase, entry.target_phrase)
        return result
