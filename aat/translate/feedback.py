"""FeedbackProvider abstraction for handling human feedback during translation."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aat.storage.models import StructuredFeedback, TranslationSegment

if TYPE_CHECKING:
    from aat.storage.checkpoints import CheckpointManager


@dataclass
class FeedbackResponse:
    """Response from a feedback provider."""
    action: str  # "approve", "revise", "skip"
    comments: list[str] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    structured_feedback: list[StructuredFeedback] = field(default_factory=list)


class FeedbackProvider(ABC):
    """Abstract base class for feedback providers."""

    @abstractmethod
    def get_feedback(self, segment: TranslationSegment) -> FeedbackResponse:
        """Get feedback for a segment. May block waiting for human input."""
        ...

    def has_pending_feedback(self, segment: TranslationSegment) -> bool:
        """Check if there is pending feedback without blocking."""
        return bool(
            segment.user_comments
            or segment.structured_feedback
            or segment.uncertainties
        )


class AutoSkipFeedbackProvider(FeedbackProvider):
    """Always skips -- preserves the original default pipeline behavior."""

    def get_feedback(self, segment: TranslationSegment) -> FeedbackResponse:
        return FeedbackResponse(action="skip")


class InteractiveCLIFeedbackProvider(FeedbackProvider):
    """Blocks on terminal, prompts user for feedback interactively."""

    def get_feedback(self, segment: TranslationSegment) -> FeedbackResponse:
        import click

        print(f"\n--- Segment {segment.segment.sid} ---", file=sys.stderr)
        print(f"Source: {segment.segment.source_text[:200]}", file=sys.stderr)
        if segment.translation:
            print(f"Translation: {segment.translation[:200]}", file=sys.stderr)
        if segment.uncertainties:
            print(f"Uncertainties: {len(segment.uncertainties)}", file=sys.stderr)

        choice = click.prompt(
            "[a]pprove / [c]omment / [s]kip",
            type=str,
        )

        if choice.lower().startswith("a"):
            return FeedbackResponse(action="approve")
        elif choice.lower().startswith("c"):
            comment = click.prompt("Enter comment")
            return FeedbackResponse(action="revise", comments=[comment])
        else:
            return FeedbackResponse(action="skip")


class CheckpointPollingFeedbackProvider(FeedbackProvider):
    """Reads feedback written by the UI into checkpoint files."""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        poll_interval: float = 2.0,
        timeout: float = 0,
    ) -> None:
        self._cm = checkpoint_manager
        self._poll_interval = poll_interval
        self._timeout = timeout

    def get_feedback(self, segment: TranslationSegment) -> FeedbackResponse:
        import time

        deadline = time.monotonic() + self._timeout

        while True:
            checkpoint = self._cm.load_latest_checkpoint()
            if checkpoint:
                sid = segment.segment.sid
                seg_data = checkpoint.segment_states.get(sid, {})
                if isinstance(seg_data, dict):
                    comments_raw = seg_data.get("user_comments", [])
                    structured_raw = seg_data.get("structured_feedback", [])
                    answers = seg_data.get("uncertainty_answers", {})
                    revision_requested = seg_data.get("revision_requested", False)

                    comments = []
                    for c in comments_raw:
                        if isinstance(c, dict):
                            comments.append(c.get("text", ""))
                        elif isinstance(c, str):
                            comments.append(c)

                    if comments or structured_raw or answers or revision_requested:
                        return FeedbackResponse(
                            action="revise",
                            comments=comments,
                            answers=answers,
                        )

            if time.monotonic() >= deadline:
                return FeedbackResponse(action="skip")

            time.sleep(self._poll_interval)
