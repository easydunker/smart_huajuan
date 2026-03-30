"""Data models for the Academic AI Translator."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class SegmenterError(Exception):
    """Exception raised for segmentation errors."""


class ValidatorStatus(str, Enum):
    """Status of validator results."""
    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


@dataclass
class Citation:
    """Represents an in-text citation."""
    cid: str
    text: str
    pid: str  # Paragraph ID


@dataclass
class Reference:
    """Represents a reference entry."""
    rid: str
    raw: str


@dataclass
class Paragraph:
    """Represents a paragraph in a section."""
    pid: str
    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Section:
    """Represents a document section."""
    heading: str | None
    paragraphs: list[Paragraph]


@dataclass
class DocumentModel:
    """Canonical document model."""
    doc_id: str
    title: str | None
    sections: list[Section]
    references: list[Reference]
    citations: list[Citation]

    @classmethod
    def create(cls) -> "DocumentModel":
        """Create a new empty document model."""
        return cls(
            doc_id=str(uuid4()),
            title=None,
            sections=[],
            references=[],
            citations=[],
        )


@dataclass
class Segment:
    """Represents a document segment for translation."""
    sid: str
    pid_list: list[str]
    source_text: str
    context_before: str | None = None
    context_after: str | None = None
    chapter_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidatorIssue:
    """Represents a validation issue."""
    code: str
    detail: str
    location: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """Result of a validation check."""
    status: ValidatorStatus
    issues: list[ValidatorIssue] = field(default_factory=list)

    def is_pass(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidatorStatus.PASS

    def is_fail(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidatorStatus.FAIL

    def is_flag(self) -> bool:
        """Check if validation has flags."""
        return self.status == ValidatorStatus.FLAG


@dataclass
class UncertaintyItem:
    """Represents an uncertainty in translation."""
    type: str  # TERM, MEANING, etc.
    span: str
    question: str
    options: list[str]


@dataclass
class DraftTranslationResult:
    """Result of a draft translation attempt."""
    translation: str
    uncertainties: list[UncertaintyItem] = field(default_factory=list)


class SegmentState(str, Enum):
    """States in the segment translation pipeline."""
    ASSEMBLE_CONTEXT = "assemble_context"
    PLANNING = "planning"
    DRAFT_TRANSLATE = "draft_translate"
    DETERMINISTIC_VALIDATE = "deterministic_validate"
    LLM_CRITIC_REVIEW = "llm_critic_review"
    UNCERTAINTY_DETECT = "uncertainty_detect"
    USER_FEEDBACK_WAIT = "user_feedback_wait"
    REVISE = "revise"
    LOCK_SEGMENT = "lock_segment"


class FeedbackCategory(str, Enum):
    """Categories for structured translation feedback."""
    WRONG_TERMINOLOGY = "wrong_terminology"
    MEANING_DRIFT = "meaning_drift"
    TONE_ISSUE = "tone_issue"
    OMISSION = "omission"
    ADDITION = "addition"
    STYLE = "style"
    OTHER = "other"


@dataclass
class StructuredFeedback:
    """A single piece of categorized feedback on a translation."""
    category: FeedbackCategory
    detail: str
    span: str | None = None
    suggested_fix: str | None = None
    timestamp: str | None = None


@dataclass
class StylePreference:
    """A style preference for translation (e.g., formality, tone)."""
    key: str
    value: str
    scope: str = "global"


@dataclass
class ProjectPreferences:
    """Project-level translation preferences."""
    terminology_overrides: dict[str, str] = field(default_factory=dict)
    style_preferences: list[StylePreference] = field(default_factory=list)


@dataclass
class TranslationSegment:
    """Represents a segment in the translation pipeline."""
    segment: Segment
    state: SegmentState
    translation: str | None = None
    uncertainties: list[UncertaintyItem] = field(default_factory=list)
    validator_results: list[ValidationResult] = field(default_factory=list)
    critic_issues: list[dict] = field(default_factory=list)
    user_comments: list[dict] = field(default_factory=list)
    translation_notes: list[str] = field(default_factory=list)
    locked: bool = False
    structured_feedback: list[StructuredFeedback] = field(default_factory=list)
    revision_requested: bool = False


@dataclass
class TermBankItem:
    """Item in the termbank."""
    source_term: str
    target_term: str
    examples: list[dict] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class TermBank:
    """Bank of terminology translations."""
    items: list[TermBankItem] = field(default_factory=list)

    def add_term(
        self,
        source_term: str,
        target_term: str,
        examples: list[dict] | None = None,
        confidence: float = 0.0,
    ) -> None:
        """Add a term to the termbank."""
        self.items.append(
            TermBankItem(
                source_term=source_term,
                target_term=target_term,
                examples=examples or [],
                confidence=confidence,
            )
        )


@dataclass
class PhraseBank:
    """Bank of academic phrase patterns."""
    functions: dict[str, list[str]] = field(default_factory=dict)

    def add_function(self, func_type: str, phrases: list[str]) -> None:
        """Add phrases for a function type."""
        if func_type not in self.functions:
            self.functions[func_type] = []
        self.functions[func_type].extend(phrases)


@dataclass
class GroundingBank:
    """Combined grounding bank."""
    termbank: TermBank = field(default_factory=TermBank)
    phrasebank: PhraseBank = field(default_factory=PhraseBank)


@dataclass
class TranslationProject:
    """Represents a translation project."""
    project_id: str
    document: DocumentModel
    segments: list[TranslationSegment] = field(default_factory=list)
    grounding: GroundingBank = field(default_factory=GroundingBank)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(cls, document: DocumentModel) -> "TranslationProject":
        """Create a new translation project."""
        return cls(project_id=str(uuid4()), document=document)
