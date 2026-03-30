# Human Reviewer Feedback Integration

> **Status:** COMPLETE
> **Prerequisite:** Option D (Web UI) complete; all existing tests green
> **Estimated effort:** 6-8 focused sessions
> **PRD reference:** Section 5.9 (Uncertainty handling), Section 5.10 (User feedback & revision loop)
> **Venv:** `./venv/bin/python` (Python 3.13)
> **Test command:** `./venv/bin/python -m pytest tests/ -q --tb=short`
> **Methodology:** Strict TDD (Red-Green-Refactor). Every phase writes failing tests FIRST, then implements code to make them pass.

---

## TDD Rules (NON-NEGOTIABLE)

1. **Red:** Write tests for the feature/change BEFORE writing any implementation code. Tests MUST fail initially (import errors, `AttributeError`, assertion failures, etc.).
2. **Green:** Write the minimum implementation code to make the failing tests pass.
3. **Refactor:** Clean up implementation while keeping tests green.
4. **No implementation without a failing test.** If you are about to write production code, ask: "Is there a failing test that requires this?" If not, write the test first.
5. **Run the full suite after every green step** to catch regressions: `./venv/bin/python -m pytest tests/ -q --tb=short`
6. **Templates are the sole exception.** HTML templates are tested via endpoint integration tests (written first in the server test file), not standalone unit tests.

---

## Before You Start

1. Confirm all existing tests pass: `./venv/bin/python -m pytest tests/ -q --tb=short`
2. Read these files to understand the current state:
   - `aat/storage/models.py` -- `TranslationSegment`, `SegmentState`, `UncertaintyItem`
   - `aat/translate/pipeline.py` -- state machine, `USER_FEEDBACK_WAIT` auto-skip at line ~247
   - `aat/translate/prompts.py` -- `RevisionPrompt` already accepts `user_feedback` and `user_answers`
   - `aat/ui/server.py` -- existing review UI with comment/edit/approve endpoints
   - `aat/ui/templates/segment_detail.html` -- "Request Revision" button is a disabled placeholder (line 160)
   - `aat/storage/checkpoints.py` -- `CheckpointManager` with write-back methods
   - `aat/translate/llm_client.py` -- `LLMClient` ABC and `FakeLLMClient` for tests

---

## Architecture Overview

```
aat translate paper.docx                     (pipeline, saves checkpoints)
    |
    |--- FeedbackProvider interface ---+
    |                                  |
    +-- AutoSkipProvider (default)     |
    +-- InteractiveCLIProvider         |      (blocks on terminal, prompts user)
    +-- CheckpointPollingProvider      |      (reads feedback written by UI)
    |                                  |
    v                                  v
USER_FEEDBACK_WAIT state ---------> REVISE state (with feedback)
    |
    v
checkpoints/*.json                           (on-disk state with feedback)
    |
    v
aat review <project_dir>                     (Web UI for post-translation review)
    |
    +-- POST /segments/{sid}/structured-feedback   -> store categorized feedback
    +-- POST /segments/{sid}/revise                -> trigger LLM revision with all feedback
    +-- GET  /preferences                          -> view project preferences
    +-- POST /preferences                          -> save terminology overrides + style
    |
    v
aat revise <project_dir>                     (CLI batch revision of segments with pending feedback)
aat set-preference <project_dir>             (CLI to set terminology/style preferences)
```

---

## Phase 0: Prerequisite Bug Fixes (1 session) ✅ DONE

> The code review identified critical bugs in existing code that must be fixed before building the feedback system. Each fix follows TDD: write a test that exposes the bug, then fix the bug to make the test pass.
>
> **Completed:** All 15 bug-fix tests pass. 506 total tests pass (from 491 baseline). Zero regressions.

### Step 0a (RED): Write tests exposing `@dataclass` on `SegmentState` Enum

Add to `tests/test_storage/test_models.py`:

1. `test_segment_state_is_enum` -- assert `isinstance(SegmentState.ASSEMBLE_CONTEXT, SegmentState)` and `isinstance(SegmentState.ASSEMBLE_CONTEXT, str)`
2. `test_segment_state_values` -- assert `SegmentState.ASSEMBLE_CONTEXT.value == "assemble_context"`, etc. for all states
3. `test_segment_state_not_dataclass` -- assert `SegmentState` does not have `__dataclass_fields__` (confirms `@dataclass` was removed)

These tests may pass on Python <3.12 (where `@dataclass` is silently ignored) but will crash on 3.12+ — either way, fix the code.

### Step 0b (GREEN): Remove `@dataclass` from `SegmentState`

In `aat/storage/models.py` line 127, remove the `@dataclass` decorator from `class SegmentState(str, Enum)`.

### Step 0c (RED): Write tests exposing `user_comments` type mismatch

Add to `tests/test_storage/test_checkpoints.py`:

4. `test_add_comment_schema_consistency` -- create checkpoint with `user_comments: []`, call `add_comment("s1", "test")`, reload, assert `user_comments` is a list of dicts with `"text"` and `"timestamp"` keys
5. `test_add_comment_to_existing_string_comments` -- create checkpoint with `user_comments: ["old comment"]`, call `add_comment("s1", "new")`, reload, assert all items are dicts (migration works correctly)
6. `test_user_comments_type_in_model_matches_checkpoint` -- assert that the `TranslationSegment.user_comments` type annotation allows both old `list[str]` and new `list[dict]` format, OR that we've settled on one format

### Step 0d (GREEN): Fix `user_comments` type mismatch

Choose one canonical format. Recommended: change `TranslationSegment.user_comments` from `list[str]` to `list[dict]` with `{"text": str, "timestamp": str}` schema. Update:
- `aat/storage/models.py` line 149: change type to `list[dict]` (or create a `UserComment` dataclass)
- `aat/cli.py` `_reconstruct_project_from_checkpoint` (line 431): handle both formats during reconstruction

### Step 0e (RED): Write tests exposing planning data silently discarded

Add to `tests/test_prompts.py`:

7. `test_draft_prompt_includes_planning_analysis` -- call `DraftTranslationPrompt.build(source_text="test", planning_analysis={"segment_type": "方法", "translation_strategy": "keep formal"})`, assert the user message contains "方法" and "keep formal"

### Step 0f (GREEN): Add `{planning}` placeholder to `DraftTranslationPrompt.USER_TEMPLATE`

In `aat/translate/prompts.py`, add a `翻译策略分析：\n{planning}` section to `DraftTranslationPrompt.USER_TEMPLATE` so that planning analysis is actually included in the prompt sent to the LLM.

### Step 0g (RED): Write tests exposing `user_answers={}` hardcode in `_revise()`

Add to `tests/test_pipeline.py`:

8. `test_revise_passes_uncertainty_answers` -- create a segment with `metadata={"uncertainty_answers": {"Q1": "Answer1"}}`, mock the LLM client, call `_revise()`, assert the prompt sent to the LLM contains "Q1" and "Answer1"

### Step 0h (GREEN): Fix `_revise()` to read answers from segment metadata

In `aat/translate/pipeline.py` `_revise()` method (line 627), change `user_answers={}` to read from `segment.segment.metadata.get("uncertainty_answers", {})`.

### Step 0i (RED): Write tests exposing context_before/context_after duplication

Add to `tests/test_prompts.py`:

9. `test_planning_prompt_separates_context_before_and_after` -- call `PlanningPrompt.build(source_text="test", context_before="before text", context_after="after text")`, assert user message contains "before text" exactly once and "after text" exactly once (not duplicated)
10. `test_draft_prompt_separates_context_before_and_after` -- same for `DraftTranslationPrompt.build()`

### Step 0j (GREEN): Fix context_before/context_after in prompt builders

In `aat/translate/prompts.py`:
- `PlanningPrompt.build()` (lines 63-80): build `context_before` and `context_after` as separate strings instead of combining both into `context_str`
- `DraftTranslationPrompt.build()` (lines 201-253): same fix

### Step 0k (RED): Write tests exposing silent write failures in UI endpoints

Add to `tests/test_ui/test_server.py`:

11. `test_approve_nonexistent_segment_returns_error` -- POST `/segments/nonexistent/approve`, assert response is NOT a success redirect (should be 404 or error message)
12. `test_edit_locked_segment_rejected` -- lock a segment, POST `/segments/{sid}/edit`, assert rejected (409 or error message)

### Step 0l (GREEN): Fix UI endpoints to check return values and locked state

In `aat/ui/server.py`:
- `approve_segment()`: check `lock_segment()` return value; if False, raise `HTTPException(404)`
- `edit_translation()`: check if segment is locked before allowing edit; if locked, raise `HTTPException(409)`
- `add_comment()`: check return value; if False, raise `HTTPException(404)`

### Step 0m (RED): Write test for `FakeLLMClient` schema-aware responses

Add to `tests/test_llm_client.py`:

13. `test_fake_client_returns_critic_schema_for_critic_review` -- call `FakeLLMClient.chat()` with `json_schema` containing `"issues"` key, assert response has `{"content": {"issues": [...]}}`
14. `test_fake_client_returns_planning_schema_for_planning` -- call with schema containing `"segment_type"` key, assert response has appropriate planning fields
15. `test_fake_client_response_queue` -- set multiple responses via a queue, assert they're returned in order on successive calls

### Step 0n (GREEN): Enhance `FakeLLMClient` with schema-awareness and response queues

In `aat/translate/llm_client.py`, update `FakeLLMClient`:
- Add `response_queue: list[dict]` attribute; if non-empty, pop and return from queue on each call
- In the default response logic, inspect `json_schema` to determine which pipeline stage is calling and return an appropriate shaped response:
  - If schema has `"issues"` key -> return `{"content": {"issues": []}}`
  - If schema has `"segment_type"` key -> return planning response
  - If schema has `"translation"` key -> return translation response (current default)

### Checkpoint 0

Run:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** All 15 new bug-fix tests pass. All existing tests still pass (fixes are backward-compatible). Zero regressions.

---

## Phase 1: Data Models (1 session) ✅ DONE

> **Completed:** All 8 new model tests pass. 514 total tests. Zero regressions.

### Step 1 (RED): Write tests for new model types

Create/update `tests/test_storage/test_models.py` with failing tests:

1. `test_feedback_category_enum_values` -- assert `FeedbackCategory.WRONG_TERMINOLOGY` etc. exist and have correct string values
2. `test_structured_feedback_creation` -- construct `StructuredFeedback(category=FeedbackCategory.OMISSION, detail="Missing sentence")`, assert fields
3. `test_structured_feedback_optional_fields` -- construct with `span=None, suggested_fix=None`, assert defaults
4. `test_style_preference_creation` -- construct `StylePreference(key="tone", value="academic")`, assert scope defaults to "global"
5. `test_project_preferences_defaults` -- construct `ProjectPreferences()`, assert empty dict and empty list
6. `test_project_preferences_with_overrides` -- construct with `terminology_overrides={"entropy": "熵"}`, assert
7. `test_translation_segment_has_structured_feedback` -- construct `TranslationSegment(...)`, assert `structured_feedback` is empty list
8. `test_translation_segment_has_revision_requested` -- construct `TranslationSegment(...)`, assert `revision_requested` is False

Run tests -- they MUST FAIL (ImportError / AttributeError since the types don't exist yet).

### Step 2 (GREEN): Implement the new model types in `aat/storage/models.py`

Add the following types after the existing `UncertaintyItem` dataclass:

1. **`FeedbackCategory(str, Enum)`:**
   - `WRONG_TERMINOLOGY = "wrong_terminology"`
   - `MEANING_DRIFT = "meaning_drift"`
   - `TONE_ISSUE = "tone_issue"`
   - `OMISSION = "omission"`
   - `ADDITION = "addition"`
   - `STYLE = "style"`
   - `OTHER = "other"`

2. **`StructuredFeedback` dataclass:**
   - `category: FeedbackCategory`
   - `detail: str`
   - `span: str | None = None` (the relevant text span in source or translation)
   - `suggested_fix: str | None = None`
   - `timestamp: str | None = None`

3. **`StylePreference` dataclass:**
   - `key: str` (e.g., "formality", "tone", "domain")
   - `value: str` (e.g., "formal", "academic", "medical")
   - `scope: str = "global"` (one of "global", "chapter", or a specific segment ID)

4. **`ProjectPreferences` dataclass:**
   - `terminology_overrides: dict[str, str] = field(default_factory=dict)` (source_term -> target_term)
   - `style_preferences: list[StylePreference] = field(default_factory=list)`

5. Add two new fields to the existing `TranslationSegment` dataclass:
   - `structured_feedback: list[StructuredFeedback] = field(default_factory=list)`
   - `revision_requested: bool = False`

### Checkpoint 1

Run:
```bash
./venv/bin/python -m pytest tests/test_storage/test_models.py -q --tb=short  # New tests pass
./venv/bin/python -m pytest tests/ -q --tb=short                              # Full suite green
```

**Pass criteria:** All new model tests pass. All existing tests still pass (no regressions from adding new fields with defaults).

---

## Phase 2: FeedbackProvider Abstraction (1.5 sessions) ✅ DONE

> **Completed:** All 14 new feedback provider tests pass (10 provider + 4 pipeline integration). 528 total tests. Zero regressions.

### Step 3 (RED): Write tests for FeedbackProvider and implementations

Create `tests/test_translate/test_feedback.py` with failing tests:

**FeedbackResponse tests:**
1. `test_feedback_response_defaults` -- construct `FeedbackResponse(action="skip")`, assert empty comments/answers/structured_feedback
2. `test_feedback_response_with_data` -- construct with comments and answers, assert all fields populated

**AutoSkipFeedbackProvider tests:**
3. `test_auto_skip_returns_skip` -- `AutoSkipFeedbackProvider().get_feedback(segment)` returns action="skip"
4. `test_auto_skip_has_no_pending_empty_segment` -- `has_pending_feedback()` returns False for segment with no comments/feedback/uncertainties
5. `test_auto_skip_has_pending_with_comments` -- `has_pending_feedback()` returns True when segment has user_comments

**InteractiveCLIFeedbackProvider tests:**
6. `test_interactive_cli_approve` -- mock `click.prompt` to return "a", assert action="approve"
7. `test_interactive_cli_comment` -- mock `click.prompt` to return "c" then comment text, assert action="revise" with comment
8. `test_interactive_cli_skip` -- mock `click.prompt` to return "s", assert action="skip"

**CheckpointPollingFeedbackProvider tests:**
9. `test_checkpoint_polling_no_feedback_returns_skip` -- no feedback in checkpoint, timeout=0, returns action="skip"
10. `test_checkpoint_polling_with_feedback_returns_revise` -- feedback present in checkpoint, returns action="revise" with that feedback

Run tests -- they MUST FAIL (ImportError since `aat/translate/feedback.py` doesn't exist yet).

### Step 4 (GREEN): Implement `aat/translate/feedback.py`

1. **`FeedbackResponse` dataclass:**
   ```python
   @dataclass
   class FeedbackResponse:
       action: str  # "approve", "revise", "skip"
       comments: list[str] = field(default_factory=list)
       answers: dict[str, str] = field(default_factory=dict)  # question -> answer
       structured_feedback: list[StructuredFeedback] = field(default_factory=list)
   ```

2. **`FeedbackProvider` ABC:**
   ```python
   class FeedbackProvider(ABC):
       @abstractmethod
       def get_feedback(self, segment: TranslationSegment) -> FeedbackResponse:
           """Get feedback for a segment. May block waiting for human input."""
           ...

       def has_pending_feedback(self, segment: TranslationSegment) -> bool:
           """Check if there is pending feedback without blocking."""
           return bool(segment.user_comments or segment.structured_feedback or segment.uncertainties)
   ```

3. **`AutoSkipFeedbackProvider`:**
   - `get_feedback()` always returns `FeedbackResponse(action="skip")`
   - This preserves the current default behavior

4. **`InteractiveCLIFeedbackProvider`:**
   - `get_feedback()` prints segment info to terminal (source text, translation, uncertainties, critic issues)
   - Uses `click.prompt` to ask user: `[a]pprove / [c]omment / [s]kip / [q]uestion answer`
   - If `c`: prompts for comment text, returns `FeedbackResponse(action="revise", comments=[text])`
   - If `a`: returns `FeedbackResponse(action="approve")`
   - If `s`: returns `FeedbackResponse(action="skip")`
   - If `q` and uncertainties exist: prompts for answer to each uncertainty question

5. **`CheckpointPollingFeedbackProvider`:**
   - Constructor takes `CheckpointManager` and `poll_interval: float = 2.0` and `timeout: float = 0`
   - `get_feedback()` checks checkpoint for segment's `revision_requested`, `user_comments`, `structured_feedback`, `uncertainty_answers`
   - If any feedback found, consumes it and returns as `FeedbackResponse(action="revise", ...)`
   - If `timeout > 0`, polls checkpoint file every `poll_interval` seconds until feedback appears or timeout
   - If `timeout == 0` (default), returns `FeedbackResponse(action="skip")` immediately when no feedback

Run `tests/test_translate/test_feedback.py` -- all 10 tests MUST PASS.

### Step 5 (RED): Write tests for pipeline integration with FeedbackProvider

Add to `tests/test_pipeline.py`:

11. `test_pipeline_accepts_feedback_provider` -- construct `TranslationPipeline(project, config, feedback_provider=mock_provider)`, assert `pipeline.feedback_provider is mock_provider`
12. `test_pipeline_default_feedback_provider_is_auto_skip` -- construct `TranslationPipeline(project, config)`, assert `isinstance(pipeline.feedback_provider, AutoSkipFeedbackProvider)`
13. `test_pipeline_approve_feedback_locks_segment` -- create a mock provider that returns action="approve", create a segment in `USER_FEEDBACK_WAIT` state, process it, assert segment is locked
14. `test_pipeline_revise_feedback_adds_comments` -- create a mock provider that returns action="revise" with comments, process segment, assert comments were added and state transitions to REVISE

Run tests -- they MUST FAIL (pipeline doesn't accept `feedback_provider` yet).

### Step 6 (GREEN): Wire FeedbackProvider into `aat/translate/pipeline.py`

1. Add `feedback_provider` parameter to `TranslationPipeline.__init__`:
   ```python
   def __init__(
       self,
       project: TranslationProject,
       config: PipelineConfig | None = None,
       feedback_provider: FeedbackProvider | None = None,
   ) -> None:
       ...
       from aat.translate.feedback import AutoSkipFeedbackProvider
       self.feedback_provider = feedback_provider or AutoSkipFeedbackProvider()
   ```

2. Replace the `USER_FEEDBACK_WAIT` handler (currently line ~243-248):
   ```python
   elif segment.state.name == "USER_FEEDBACK_WAIT":
       response = self.feedback_provider.get_feedback(segment)
       if response.action == "approve":
           segment.state = SegmentState.LOCK_SEGMENT
       elif response.action == "revise":
           segment.user_comments.extend(response.comments)
           segment.structured_feedback.extend(response.structured_feedback)
           if response.answers:
               if not segment.segment.metadata:
                   segment.segment.metadata = {}
               existing_answers = segment.segment.metadata.get("uncertainty_answers", {})
               existing_answers.update(response.answers)
               segment.segment.metadata["uncertainty_answers"] = existing_answers
           segment.state = SegmentState.REVISE
       else:  # skip
           segment.state = SegmentState.REVISE
   ```

3. Update `_revise()` to pass structured feedback and project preferences into the revision prompt:
   - Extract `structured_feedback` from the segment
   - Format as list of dicts for the prompt
   - Load project preferences from `self.project` metadata or a separate config
   - Pass both to `RevisionPrompt.build()`

### Checkpoint 2

Run:
```bash
./venv/bin/python -m pytest tests/test_translate/test_feedback.py -q --tb=short  # All provider tests pass
./venv/bin/python -m pytest tests/test_pipeline.py -q --tb=short                 # All pipeline tests pass
./venv/bin/python -m pytest tests/ -q --tb=short                                  # Full suite green
```

**Pass criteria:** All new + existing tests pass. Default `AutoSkipFeedbackProvider` preserves current behavior.

---

## Phase 3: Checkpoint & Storage Enhancements (0.5 session) ✅ DONE

> **Completed:** All 9 new checkpoint tests pass. 537 total tests. Zero regressions.

### Step 7 (RED): Write tests for new checkpoint features

Add to `tests/test_storage/test_checkpoints.py`:

1. `test_checkpoint_has_preferences_field` -- construct `Checkpoint(...)`, assert `preferences` defaults to `{}`
2. `test_checkpoint_to_json_includes_preferences` -- create checkpoint with preferences, `to_json()` output contains "preferences" key
3. `test_checkpoint_from_json_reads_preferences` -- roundtrip: `to_json()` then `from_json()`, assert preferences preserved
4. `test_checkpoint_from_json_backward_compat` -- `from_json()` on old JSON without "preferences" key, assert `preferences == {}`
5. `test_request_revision_sets_flags` -- `request_revision("s1")`, reload, assert segment has `revision_requested=True`, `state="user_feedback_wait"`, `locked=False`
6. `test_add_structured_feedback_appends` -- `add_structured_feedback("s1", "OMISSION", "Missing sentence")`, reload, assert feedback list has 1 item with correct fields
7. `test_add_structured_feedback_multiple` -- call twice, assert list has 2 items
8. `test_set_project_preferences_roundtrip` -- `set_project_preferences({"terminology_overrides": {"entropy": "熵"}})`, `get_project_preferences()` returns same dict
9. `test_get_project_preferences_empty_default` -- no preferences set, `get_project_preferences()` returns `{}`

Run tests -- they MUST FAIL (new fields/methods don't exist yet).

### Step 8 (GREEN): Implement checkpoint enhancements in `aat/storage/checkpoints.py`

1. Add `preferences: dict` field to `Checkpoint`:
   ```python
   @dataclass
   class Checkpoint:
       project_id: str
       timestamp: str
       segment_states: dict
       metadata: dict
       preferences: dict = field(default_factory=dict)  # NEW
   ```

2. Update `to_json()` to include `preferences` in the output dict.

3. Update `from_json()` to read `preferences` (with `data.get("preferences", {})` for backward compatibility).

4. Add new methods to `CheckpointManager`:

   - **`request_revision(sid: str) -> bool`:**
     - Calls `self.update_segment(sid, {"revision_requested": True, "state": "user_feedback_wait", "locked": False})`

   - **`add_structured_feedback(sid: str, category: str, detail: str, span: str | None = None, suggested_fix: str | None = None) -> bool`:**
     - Load latest checkpoint
     - Get segment state for `sid`
     - Append feedback dict to `seg["structured_feedback"]` list (create if missing)
     - Save checkpoint

   - **`set_project_preferences(preferences: dict) -> bool`:**
     - Load latest checkpoint
     - Set `checkpoint.preferences = preferences`
     - Save checkpoint

   - **`get_project_preferences() -> dict`:**
     - Load latest checkpoint
     - Return `checkpoint.preferences` or `{}`

### Checkpoint 3

Run:
```bash
./venv/bin/python -m pytest tests/test_storage/test_checkpoints.py -q --tb=short  # All checkpoint tests pass
./venv/bin/python -m pytest tests/ -q --tb=short                                   # Full suite green
```

**Pass criteria:** All tests pass. Old checkpoints without `preferences` field load correctly.

---

## Phase 4: Enhanced Prompts (0.5 session) ✅ DONE

> **Completed:** All 7 new prompt tests pass. 544 total tests. Zero regressions.

### Step 9 (RED): Write tests for enhanced prompts

Add to `tests/test_prompts.py`:

1. `test_revision_prompt_accepts_structured_feedback` -- call `RevisionPrompt.build(...)` with `structured_feedback=[{"category": "OMISSION", "detail": "Missing sentence"}]`, assert the user message contains "OMISSION" and "Missing sentence"
2. `test_revision_prompt_accepts_style_preferences` -- call with `style_preferences={"formality": "formal", "tone": "academic"}`, assert user message contains "formal" and "academic"
3. `test_revision_prompt_structured_feedback_none_is_ok` -- call with `structured_feedback=None`, assert no error and message contains "无" or similar placeholder
4. `test_revision_prompt_style_preferences_none_is_ok` -- call with `style_preferences=None`, assert no error
5. `test_draft_prompt_accepts_style_preferences` -- call `DraftTranslationPrompt.build(...)` with `style_preferences={"terminology_overrides": {"entropy": "熵"}}`, assert user message contains "entropy" and "熵"
6. `test_draft_prompt_merges_term_overrides_into_termbank` -- call with both `termbank={"foo": "bar"}` and `style_preferences={"terminology_overrides": {"baz": "qux"}}`, assert both appear in user message
7. `test_existing_revision_prompt_build_unchanged` -- call `RevisionPrompt.build()` with only the original params (no new ones), assert it still works (backward compat)

Run tests -- they MUST FAIL (new params not accepted yet).

### Step 10 (GREEN): Update `aat/translate/prompts.py`

1. **Update `RevisionPrompt.USER_TEMPLATE`** to include structured feedback and style preferences:
   ```
   请根据以下反馈修订翻译：

   原文：
   {source_text}

   当前译文：
   {current_translation}

   审稿意见：
   {critic_issues}

   用户反馈：
   {user_feedback}

   结构化反馈：
   {structured_feedback}

   用户问题答案：
   {user_answers}

   风格偏好：
   {style_preferences}

   术语库（如果有）：
   {termbank}
   ```

2. **Update `RevisionPrompt.build()` signature:**
   ```python
   @staticmethod
   def build(
       source_text: str,
       current_translation: str,
       critic_issues: list[dict],
       user_feedback: list[str],
       user_answers: dict[str, str],
       termbank: dict[str, Any] | None = None,
       structured_feedback: list[dict] | None = None,  # NEW
       style_preferences: dict | None = None,  # NEW
   ) -> list[dict]:
   ```
   - Format `structured_feedback` as: `"- [WRONG_TERMINOLOGY] 'entropy' should be '熵' not '信息熵' (建议修改: 熵)"`
   - Format `style_preferences` as: `"- 正式程度: formal\n- 语气: academic"`

3. **Update `DraftTranslationPrompt.build()` signature** to accept optional `style_preferences: dict`:
   - Merge `terminology_overrides` from preferences into `termbank`
   - Add tone/formality instructions to the system prompt section

### Checkpoint 4

Run:
```bash
./venv/bin/python -m pytest tests/test_prompts.py -q --tb=short  # All prompt tests pass
./venv/bin/python -m pytest tests/ -q --tb=short                  # Full suite green
```

**Pass criteria:** All tests pass. Existing calls to `RevisionPrompt.build()` and `DraftTranslationPrompt.build()` still work (new params have defaults).

---

## Phase 5: UI Server Endpoints (1 session) ✅ DONE

> **Completed:** All 11 new UI endpoint tests pass. 555 total tests. Zero regressions.

### Step 11 (RED): Write tests for new UI endpoints

Create `tests/test_ui/test_revision.py` using `FastAPI TestClient`. Use a fixture that creates a test checkpoint in `tmp_path` and initializes the app (same pattern as `tests/test_ui/test_server.py`).

1. `test_structured_feedback_endpoint_stores_feedback` -- POST to `/segments/s1/structured-feedback` with form data `category=OMISSION&detail=Missing+sentence`, follow redirect, reload checkpoint, assert feedback stored
2. `test_structured_feedback_with_optional_fields` -- POST with `span=test+span&suggested_fix=add+it`, assert stored with all fields
3. `test_structured_feedback_appears_in_segment_data` -- store feedback, call `loader.get_segment("s1")`, assert `structured_feedback` is non-empty
4. `test_revise_endpoint_updates_translation` -- POST to `/segments/s1/revise`, assert translation changed in checkpoint (uses `FakeLLMClient`)
5. `test_revise_endpoint_not_initialized` -- don't call `create_app()`, POST to `/segments/s1/revise`, assert 503
6. `test_preferences_page_loads` -- GET `/preferences` returns 200
7. `test_save_preferences_style` -- POST `/preferences` with `formality=formal&tone=academic`, GET `/preferences`, assert values persisted
8. `test_add_term_override` -- POST `/preferences/term` with `source=entropy&target=熵`, reload preferences, assert terminology_overrides contains entry
9. `test_delete_term_override` -- add a term, then POST `/preferences/term/delete` with `source=entropy`, assert removed
10. `test_needs_revision_filter` -- set `revision_requested=True` on one segment, GET `/segments?filter=needs_revision`, assert only that segment returned

Add to `tests/test_ui/test_server.py`:

11. `test_segment_detail_shows_structured_feedback_section` -- GET `/segments/s1`, assert response HTML contains "Structured Feedback"
12. `test_preferences_link_in_nav` -- GET `/segments`, assert response HTML contains `href="/preferences"`

Run tests -- they MUST FAIL (endpoints and template changes don't exist yet).

### Step 12 (GREEN): Implement server endpoints and ProjectLoader updates

**Add to `aat/ui/server.py`:**

**`POST /segments/{sid}/revise`:**
1. Check initialized
2. Load segment data from checkpoint
3. Collect all feedback: `user_comments`, `structured_feedback`, `uncertainty_answers`
4. Load project preferences
5. Instantiate LLM client (use config from environment or defaults; fall back to FakeLLMClient in tests)
6. Build `RevisionPrompt` with all collected feedback + preferences
7. Call LLM
8. Parse response, update translation in checkpoint
9. Clear `revision_requested` flag
10. Reload loader
11. Redirect back to `/segments/{sid}?msg=Revision+complete`

**`POST /segments/{sid}/structured-feedback`:**
```python
@app.post("/segments/{sid}/structured-feedback")
async def add_structured_feedback(
    sid: str,
    category: str = Form(...),
    detail: str = Form(...),
    span: str = Form(""),
    suggested_fix: str = Form(""),
):
    _check_initialized()
    checkpoint_manager.add_structured_feedback(
        sid, category, detail,
        span=span or None,
        suggested_fix=suggested_fix or None,
    )
    loader.reload()
    return RedirectResponse(url=f"/segments/{sid}?msg=Feedback+added", status_code=303)
```

**Preferences endpoints:**
- `GET /preferences` -- render `preferences.html`
- `POST /preferences` -- save style preferences
- `POST /preferences/term` -- add/update terminology override
- `POST /preferences/term/delete` -- remove terminology override

**Update `ProjectLoader`:**
- `get_segments()` and `get_segment()` now also return `structured_feedback` and `revision_requested` fields
- New `get_preferences()` method returns `checkpoint.preferences`
- `list_segments()` supports new filter `state_filter="needs_revision"` -- returns segments where `revision_requested` is True or `structured_feedback` is non-empty

### Checkpoint 5

Run:
```bash
./venv/bin/python -m pytest tests/test_ui/test_revision.py -q --tb=short  # All new endpoint tests pass
./venv/bin/python -m pytest tests/test_ui/ -q --tb=short                   # All UI tests pass
./venv/bin/python -m pytest tests/ -q --tb=short                            # Full suite green
```

**Pass criteria:** All tests pass.

---

## Phase 6: UI Templates (1 session) ✅ DONE

> **Completed:** Templates implemented alongside Phase 5. Tests verified via endpoint integration tests.

> Templates are tested via the endpoint integration tests written in Phase 5 (Step 11). The RED tests from Step 11 that check HTML content (e.g., `test_segment_detail_shows_structured_feedback_section`, `test_preferences_link_in_nav`) serve as the failing tests for this phase. Implement the templates to make those tests GREEN.

### Step 13: Update `aat/ui/templates/segment_detail.html`

1. **Enable "Request Revision" button** (replace the disabled placeholder at line 160):
   ```html
   <form method="POST" action="/segments/{{ seg.sid }}/revise">
     <button type="submit" class="btn btn-outline"
       {% if seg.locked %}disabled{% endif %}>
       Request Revision
     </button>
   </form>
   ```

2. **Add structured feedback section** (after the comments section):
   ```html
   <div class="section">
     <h3>Structured Feedback</h3>
     {% if seg.structured_feedback %}
       {% for fb in seg.structured_feedback %}
       <div class="issue-item">
         <span class="badge badge-{{ fb.category|lower }}">{{ fb.category }}</span>
         {{ fb.detail }}
         {% if fb.span %}<br><em>Span: {{ fb.span }}</em>{% endif %}
         {% if fb.suggested_fix %}<br><strong>Suggested: {{ fb.suggested_fix }}</strong>{% endif %}
       </div>
       {% endfor %}
     {% else %}
       <p style="color:#999;font-size:0.9rem">No structured feedback yet.</p>
     {% endif %}
     <form method="POST" action="/segments/{{ seg.sid }}/structured-feedback" style="margin-top:0.5rem">
       <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:flex-start">
         <select name="category" style="padding:0.4em;border:1px solid #ccc;border-radius:4px">
           <option value="WRONG_TERMINOLOGY">Wrong Terminology</option>
           <option value="MEANING_DRIFT">Meaning Drift</option>
           <option value="TONE_ISSUE">Tone Issue</option>
           <option value="OMISSION">Omission</option>
           <option value="ADDITION">Addition</option>
           <option value="STYLE">Style</option>
           <option value="OTHER">Other</option>
         </select>
         <input name="detail" placeholder="Describe the issue..." style="flex:1;min-width:200px;padding:0.4em;border:1px solid #ccc;border-radius:4px" required>
         <input name="span" placeholder="Text span (optional)" style="width:150px;padding:0.4em;border:1px solid #ccc;border-radius:4px">
         <input name="suggested_fix" placeholder="Suggested fix (optional)" style="width:150px;padding:0.4em;border:1px solid #ccc;border-radius:4px">
         <button type="submit" class="btn btn-primary">Submit</button>
       </div>
     </form>
   </div>
   ```

3. **Show revision history** if available in segment metadata `revision_history`.

### Step 14: Create `aat/ui/templates/preferences.html`

Extends `base.html`. Content:

1. **Terminology Overrides section:**
   - Table with columns: Source Term | Target Term | Actions (delete)
   - Add form at bottom: source input + target input + Add button
   - Form POSTs to `/preferences/term`

2. **Style Settings section:**
   - Formality dropdown: Formal / Semi-formal / Informal
   - Tone dropdown: Academic / Technical / General
   - Domain input: free text (e.g., "computer science", "medicine")
   - Save button POSTs to `/preferences`

### Step 15: Update `aat/ui/templates/base.html`

Add "Preferences" link to nav bar (after the "Terminology" link):
```html
<a href="/preferences">Preferences</a>
```

### Step 16: Update `aat/ui/templates/segments.html`

Add "Needs Revision" filter button:
```html
<a href="/segments?filter=needs_revision" {% if filter == 'needs_revision' %}class="active"{% endif %}>Needs Revision</a>
```

### Step 17: Add CSS for feedback category badges to `base.html`

```css
.badge-wrong_terminology { background: #f8d7da; color: #721c24; }
.badge-meaning_drift { background: #fff3cd; color: #856404; }
.badge-tone_issue { background: #d1ecf1; color: #0c5460; }
.badge-omission { background: #f5c6cb; color: #721c24; }
.badge-addition { background: #ffeeba; color: #856404; }
.badge-style { background: #d4edda; color: #155724; }
.badge-other { background: #e2e3e5; color: #383d41; }
```

### Checkpoint 6

**Manual check:** Start server, verify:
1. Structured feedback form appears on segment detail page
2. Submitting feedback stores it and shows badge
3. "Request Revision" button triggers LLM revision (use FakeLLMClient for testing)
4. Preferences page shows terminology table and style settings
5. "Needs Revision" filter works on segment list

---

## Phase 7: CLI Commands (1 session) ✅ DONE

> **Completed:** All 8 new CLI tests pass. 563 total tests. Zero regressions.

### Step 18 (RED): Write tests for new CLI commands

Add to `tests/test_cli.py` using Click's `CliRunner`:

1. `test_translate_accepts_interactive_flag` -- invoke `aat translate --help`, assert output contains `--interactive`
2. `test_revise_command_exists` -- invoke `aat revise --help`, assert exit code 0 and output contains "Revise segments"
3. `test_revise_requires_project_folder` -- invoke `aat revise` with no args, assert exit code != 0
4. `test_revise_nonexistent_folder` -- invoke `aat revise /nonexistent`, assert exit code != 0
5. `test_revise_all_with_checkpoint` -- create checkpoint in `tmp_path` with feedback on a segment, invoke `aat revise tmp_path --all`, assert output contains "Revised" (uses FakeLLMClient via env/config)
6. `test_set_preference_command_exists` -- invoke `aat set-preference --help`, assert exit code 0 and output contains "Set project-level"
7. `test_set_preference_term` -- create checkpoint in `tmp_path`, invoke `aat set-preference tmp_path --term "entropy=熵"`, reload checkpoint, assert terminology_overrides contains "entropy"
8. `test_set_preference_tone` -- invoke `aat set-preference tmp_path --tone academic`, reload checkpoint, assert style preferences contain tone=academic

Run tests -- they MUST FAIL (commands don't exist yet).

### Step 19 (GREEN): Implement CLI commands in `aat/cli.py`

**Add `--interactive` flag to `aat translate`:**

```python
@click.option("--interactive", is_flag=True, help="Pause for human feedback at each segment")
```

In the translate handler, when `interactive=True`:
```python
from aat.translate.feedback import InteractiveCLIFeedbackProvider
feedback_provider = InteractiveCLIFeedbackProvider() if interactive else None
pipeline = TranslationPipeline(project, config=config, feedback_provider=feedback_provider)
```

**Add `aat revise` command:**

```python
@main.command()
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--all", "revise_all", is_flag=True, help="Revise all segments with pending feedback")
@click.option("--segment", "segment_id", type=str, help="Revise a specific segment by ID")
def revise(project_folder: str, revise_all: bool, segment_id: str | None) -> None:
    """Revise segments using accumulated human feedback."""
```

Implementation:
1. Load checkpoint
2. Reconstruct project from checkpoint
3. Find segments with pending feedback (or specific segment if `--segment` given)
4. For each segment:
   - Load all feedback (comments, structured feedback, uncertainty answers)
   - Load project preferences
   - Build `RevisionPrompt` with all feedback
   - Call LLM
   - Update checkpoint with revised translation
   - Clear `revision_requested` flag
5. Print summary: `Revised N segments`

**Add `aat set-preference` command:**

```python
@main.command(name="set-preference")
@click.argument("project_folder", type=click.Path(exists=True))
@click.option("--term", type=str, help="Add terminology override (format: source=target)")
@click.option("--tone", type=click.Choice(["academic", "technical", "general"]))
@click.option("--formality", type=click.Choice(["formal", "semi-formal", "informal"]))
def set_preference(project_folder: str, term: str | None, tone: str | None, formality: str | None) -> None:
    """Set project-level translation preferences."""
```

### Checkpoint 7

Run:
```bash
./venv/bin/python -m pytest tests/test_cli.py -q --tb=short  # All CLI tests pass
./venv/bin/python -m pytest tests/ -q --tb=short               # Full suite green
```

**Pass criteria:** All tests pass.

---

## Phase 8: Test Consolidation & Coverage (0.5 session) ✅ DONE

> **Completed:** 5 edge-case/integration tests added. Final count: 568 passed, 1 skipped, 0 failures. Zero regressions.

> By this point, all tests have already been written and are passing (TDD was enforced in every phase). This phase is for adding edge-case tests, verifying coverage thresholds, and adding any integration tests that span multiple phases.

### Step 20: Add edge-case and integration tests

**Add to `tests/test_translate/test_feedback.py`:**

1. `test_feedback_response_invalid_action` -- construct with action="invalid", verify it doesn't crash (it's just a data container; validation happens in pipeline)
2. `test_interactive_cli_with_uncertainties_answers` -- mock stdin "q" + answers for each uncertainty, assert answers dict populated
3. `test_checkpoint_polling_timeout_zero_returns_immediately` -- with timeout=0 and no feedback, verify get_feedback returns in <100ms

**Add to `tests/test_ui/test_revision.py`:**

4. `test_revise_segment_not_found` -- POST `/segments/nonexistent/revise`, assert 404
5. `test_structured_feedback_missing_required_field` -- POST without `detail`, assert 422 validation error

**Add end-to-end integration test to `tests/test_translate/test_feedback.py`:**

6. `test_full_feedback_loop_e2e` -- Create project with FakeLLMClient, run pipeline with a mock FeedbackProvider that returns "revise" with structured feedback on first call then "approve" on second call. Assert: segment gets revised translation, then gets locked. Verify structured_feedback was passed through to revision.

### Step 21: Verify coverage

Run:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short --cov=aat --cov-report=term-missing
```

**Pass criteria:**
- All tests pass, 0 failures
- Overall coverage >= 85%
- `aat/translate/feedback.py` coverage >= 95%
- `aat/translate/pipeline.py` coverage >= 95%
- No untested public methods in new code

### Checkpoint 8 (Final)

Run:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** All tests pass (existing + new), 0 failures, coverage thresholds met.

---

## TDD Summary by Phase

| Phase | RED (write failing tests) | GREEN (implement to pass) |
|-------|--------------------------|--------------------------|
| 0: Bug Fixes | Steps 0a,0c,0e,0g,0i,0k,0m: 15 bug-exposing tests | Steps 0b,0d,0f,0h,0j,0l,0n: fix each bug |
| 1: Models | Step 1: 8 model tests | Step 2: models.py types |
| 2: Feedback | Step 3: 10 provider tests, Step 5: 4 pipeline tests | Step 4: feedback.py, Step 6: pipeline.py |
| 3: Checkpoints | Step 7: 9 checkpoint tests | Step 8: checkpoints.py |
| 4: Prompts | Step 9: 7 prompt tests | Step 10: prompts.py |
| 5: UI Server | Step 11: 12 endpoint tests | Step 12: server.py |
| 6: Templates | (covered by Step 11 endpoint tests) | Steps 13-17: HTML templates |
| 7: CLI | Step 18: 8 CLI tests | Step 19: cli.py |
| 8: Consolidation | Step 20: 6 edge-case/integration tests | (already implemented) |

**Total new tests: ~79** (15 bug-fix + 64 feature)

---

## Files to Create

| File | Purpose |
|------|---------|
| `aat/translate/feedback.py` | FeedbackProvider ABC + 3 implementations |
| `aat/ui/templates/preferences.html` | Project preferences page template |
| `tests/test_translate/test_feedback.py` | Tests for feedback providers (10+ tests) |
| `tests/test_ui/test_revision.py` | Tests for revision + feedback endpoints (8+ tests) |

## Files to Modify

| File | Phase 0 (Bug Fix) | Phases 1-7 (Feature) |
|------|-------------------|---------------------|
| `aat/storage/models.py` | Remove `@dataclass` from `SegmentState`; fix `user_comments` type | Add FeedbackCategory, StructuredFeedback, StylePreference, ProjectPreferences; update TranslationSegment |
| `aat/translate/prompts.py` | Add `{planning}` placeholder to DraftTranslationPrompt; fix context_before/after duplication | Update RevisionPrompt and DraftTranslationPrompt for structured feedback + preferences |
| `aat/translate/pipeline.py` | Fix `user_answers={}` hardcode in `_revise()` | Add feedback_provider param; replace auto-skip with provider call |
| `aat/translate/llm_client.py` | Add schema-awareness and response queues to FakeLLMClient | — |
| `aat/ui/server.py` | Check return values on write endpoints; reject edits to locked segments | Add /revise, /structured-feedback, /preferences endpoints; update ProjectLoader |
| `aat/cli.py` | Fix `_reconstruct_project_from_checkpoint` for new user_comments format | Add --interactive flag, aat revise command, aat set-preference command |
| `aat/storage/checkpoints.py` | — | Add preferences field; add request_revision, add_structured_feedback, preference methods |
| `aat/ui/templates/segment_detail.html` | — | Enable revision button, add structured feedback form + display |
| `aat/ui/templates/segments.html` | — | Add "Needs Revision" filter |
| `aat/ui/templates/base.html` | — | Add "Preferences" nav link, add feedback category badge CSS |
| `tests/test_storage/test_models.py` | 3 SegmentState tests | 8 new model type tests |
| `tests/test_storage/test_checkpoints.py` | 3 user_comments tests | 9 checkpoint enhancement tests |
| `tests/test_prompts.py` | 4 prompt bug tests | 7 prompt enhancement tests |
| `tests/test_pipeline.py` | 1 user_answers test | 4 feedback_provider tests |
| `tests/test_ui/test_server.py` | 2 endpoint validation tests | 2 new feature tests |
| `tests/test_llm_client.py` | 3 FakeLLMClient tests | — |

---

## Relationship to Other Plans

- **Option D (Web UI):** This plan extends the review UI built in Option D. All Option D features are prerequisites.
- **Option C (Quality):** Quality heuristic results can inform structured feedback categories. Not a hard dependency.
- **Option B (M6 Global Pass):** Global pass could be extended to incorporate project preferences for consistency checks. Additive, not blocking.
- **PRD Section 5.9/5.10:** This plan implements the full user feedback & revision loop specified in the PRD, including uncertainty handling, comments, and the revise-until-lock cycle.
