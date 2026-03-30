# Code Review Fix Plan

> **Status:** PENDING
> **Prerequisite:** Human Feedback Plan complete; 568 tests green
> **Venv:** `./venv/bin/python` (Python 3.13)
> **Test command:** `./venv/bin/python -m pytest tests/ -q --tb=short`
> **Methodology:** Strict TDD. Every fix writes a failing test FIRST, then implements the fix.

---

## Fix Priority Tiers

| Tier | Description | Count |
|------|-------------|-------|
| P0 – Critical | Data flow breaks that prevent the feature from working end-to-end | 5 |
| P1 – High | Important gaps that lose data or silently fail | 6 |
| P2 – Major | Correctness, validation, and robustness issues | 9 |
| P3 – Minor/Nit | Polish, naming, accessibility, style | Deferred |

---

## P0 – Critical Fixes (5)

### Fix 1: Pipeline extends `user_comments` with strings instead of dicts

**Files:** `aat/translate/pipeline.py` (line 254)
**Bug:** `segment.user_comments.extend(response.comments)` appends `list[str]` into a `list[dict]` field, creating mixed types that break serialization and display.

**Test (RED):** `tests/test_pipeline.py`
```
test_pipeline_revise_feedback_comments_are_dicts
  – Provider returns comments=["fix this"]. After processing, assert every
    item in segment.user_comments is a dict with "text" and "timestamp" keys.
```

**Fix (GREEN):** In `pipeline.py` USER_FEEDBACK_WAIT handler, replace:
```python
segment.user_comments.extend(response.comments)
```
with:
```python
from datetime import datetime
for c in response.comments:
    segment.user_comments.append({"text": c, "timestamp": datetime.now().isoformat()})
```

---

### Fix 2: Pipeline `_revise()` passes `user_comments` (dicts) as `user_feedback` (expects strings)

**Files:** `aat/translate/pipeline.py` (line 642)
**Bug:** `_revise()` passes `segment.user_comments` (list of dicts like `{"text": "...", "timestamp": "..."}`) to `RevisionPrompt.build(user_feedback=...)`, which expects `list[str]` and joins them. The LLM sees `"{'text': 'x', 'timestamp': 'y'}"` instead of the comment text.

**Test (RED):** `tests/test_pipeline.py`
```
test_revise_sends_comment_text_not_dicts
  – Create segment with user_comments=[{"text": "fix tone", "timestamp": "now"}].
    Use a CapturingClient. Call _revise(). Assert "fix tone" appears in the
    user message AND the raw dict repr does NOT appear.
```

**Fix (GREEN):** In `_revise()`, extract text before passing:
```python
user_feedback=[
    c.get("text", str(c)) if isinstance(c, dict) else str(c)
    for c in segment.user_comments
],
```

---

### Fix 3: Pipeline `_revise()` omits `structured_feedback` and `style_preferences`

**Files:** `aat/translate/pipeline.py` (lines 638–645)
**Bug:** `RevisionPrompt.build()` accepts `structured_feedback` and `style_preferences`, but `_revise()` never passes them. In-pipeline revisions ignore all structured feedback and project preferences.

**Test (RED):** `tests/test_pipeline.py`
```
test_revise_passes_structured_feedback_to_prompt
  – Create segment with structured_feedback=[StructuredFeedback(...)].
    Use CapturingClient. Call _revise(). Assert the structured feedback
    category and detail appear in the prompt sent to the LLM.

test_revise_passes_style_preferences_to_prompt
  – Set up pipeline with checkpoint_manager that has preferences.
    Call _revise(). Assert preference keys appear in the prompt.
```

**Fix (GREEN):** In `_revise()`, add to the `RevisionPrompt.build()` call:
```python
structured_feedback=[
    {"category": fb.category.value if hasattr(fb.category, "value") else str(fb.category),
     "detail": fb.detail, "span": fb.span, "suggested_fix": fb.suggested_fix}
    for fb in segment.structured_feedback
] if segment.structured_feedback else None,
style_preferences=(
    self.checkpoint_manager.get_project_preferences()
    if self.checkpoint_manager else None
),
```

---

### Fix 4: `CheckpointPollingFeedbackProvider` drops `structured_feedback`

**Files:** `aat/translate/feedback.py` (lines 112–117)
**Bug:** Reads `structured_raw` from checkpoint and uses it in the condition, but never passes it into `FeedbackResponse`. The pipeline gets an empty list.

**Test (RED):** `tests/test_translate/test_feedback.py`
```
test_checkpoint_polling_with_structured_feedback_returns_it
  – Create checkpoint with structured_feedback=[{"category": "OMISSION", "detail": "missing"}]
    on segment s1. Create provider. Call get_feedback(). Assert
    response.structured_feedback is non-empty and contains the feedback.
```

**Fix (GREEN):** In `CheckpointPollingFeedbackProvider.get_feedback()`, parse and include:
```python
from aat.storage.models import FeedbackCategory, StructuredFeedback

structured_feedback = []
for fb in structured_raw:
    if isinstance(fb, dict):
        try:
            cat = FeedbackCategory(fb.get("category", "other").lower())
        except ValueError:
            cat = FeedbackCategory.OTHER
        structured_feedback.append(StructuredFeedback(
            category=cat, detail=fb.get("detail", ""),
            span=fb.get("span"), suggested_fix=fb.get("suggested_fix"),
            timestamp=fb.get("timestamp"),
        ))

# In the FeedbackResponse:
return FeedbackResponse(
    action="revise", comments=comments,
    answers=answers, structured_feedback=structured_feedback,
)
```

---

### Fix 5: `FakeLLMClient` hardcoded in production revise endpoints

**Files:** `aat/ui/server.py` (line 260), `aat/cli.py` (line 749)
**Bug:** Both `/segments/{sid}/revise` and `aat revise` always use `FakeLLMClient()`, returning mock translations. Real LLM output is never produced.

**Test (RED):** `tests/test_ui/test_revision.py`, `tests/test_cli.py`
```
test_revise_endpoint_uses_configured_llm_client
  – Inject a test client into the app and verify the configured client is called.

test_revise_cli_uses_configured_provider
  – Mock create_client and verify it is called with the correct provider.
```

**Fix (GREEN):**

In `server.py`: Add a module-level `llm_client` variable set by `create_app()` (or lazy-init from config), replacing `FakeLLMClient()` in `revise_segment()`:
```python
# In create_app():
from aat.translate.llm_client import create_client
global llm_client
llm_client = create_client(provider="fake")  # default for tests
# In revise_segment():
client = llm_client or FakeLLMClient()
```

In `cli.py`: Read provider config from `~/.aat/config.toml` or env vars:
```python
from aat.translate.llm_client import create_client
provider = os.environ.get("AAT_LLM_PROVIDER", "fake")
model = os.environ.get("AAT_LLM_MODEL", "claude-3-5-sonnet-20241022")
llm_client = create_client(provider=provider, model=model)
```

---

## P1 – High-Priority Fixes (6)

### Fix 6: `--interactive` flag not wired to pipeline

**Files:** `aat/cli.py` (line 36)
**Bug:** The flag is defined but `InteractiveCLIFeedbackProvider` is never instantiated.

**Test (RED):** `tests/test_cli.py`
```
test_translate_interactive_creates_interactive_provider
  – Mock the pipeline constructor. Invoke translate with --interactive.
    Assert feedback_provider is InteractiveCLIFeedbackProvider.
```

**Fix (GREEN):** In the translate handler, after creating config:
```python
feedback_provider = None
if interactive:
    from aat.translate.feedback import InteractiveCLIFeedbackProvider
    feedback_provider = InteractiveCLIFeedbackProvider()
pipeline = TranslationPipeline(project, config=config, feedback_provider=feedback_provider)
```

---

### Fix 7: `RevisionPrompt` doesn't merge `terminology_overrides` into termbank

**Files:** `aat/translate/prompts.py` (lines 536–541)
**Bug:** `DraftTranslationPrompt` merges terminology_overrides from style_preferences into termbank, but `RevisionPrompt` doesn't. Terminology overrides are excluded from style_preferences display and never reach the LLM.

**Test (RED):** `tests/test_prompts.py`
```
test_revision_prompt_merges_terminology_overrides_into_termbank
  – Call RevisionPrompt.build() with style_preferences={"terminology_overrides": {"entropy": "熵"}}.
    Assert "entropy" and "熵" appear in the user message.
```

**Fix (GREEN):** In `RevisionPrompt.build()`, before building termbank_str:
```python
merged_termbank = dict(termbank) if termbank else {}
if style_preferences and "terminology_overrides" in style_preferences:
    merged_termbank.update(style_preferences["terminology_overrides"])
# Build termbank_str from merged_termbank instead of termbank
```

---

### Fix 8: `_reconstruct_project_from_checkpoint` omits new fields

**Files:** `aat/cli.py` (lines 424–434)
**Bug:** `structured_feedback`, `revision_requested`, and `translation_notes` are not reconstructed. `aat export` and `aat resume` lose feedback data.

**Test (RED):** `tests/test_cli.py`
```
test_reconstruct_includes_structured_feedback_and_revision_requested
  – Create checkpoint with structured_feedback and revision_requested on a segment.
    Call _reconstruct_project_from_checkpoint(). Assert the TranslationSegment
    has non-empty structured_feedback and revision_requested=True.
```

**Fix (GREEN):** In `_reconstruct_project_from_checkpoint`, add to the `TranslationSegment` constructor:
```python
structured_feedback=[...deserialize from state_data...],
revision_requested=state_data.get("revision_requested", False),
translation_notes=state_data.get("translation_notes", []),
```

---

### Fix 9: No exception handling for `feedback_provider.get_feedback()`

**Files:** `aat/translate/pipeline.py` (line 248)
**Bug:** Provider errors propagate uncaught, leaving segments in inconsistent state.

**Test (RED):** `tests/test_pipeline.py`
```
test_feedback_provider_exception_raises_pipeline_error
  – Create a provider whose get_feedback() raises RuntimeError.
    Process a segment. Assert PipelineError is raised.
```

**Fix (GREEN):** Wrap in try/except:
```python
try:
    response = self.feedback_provider.get_feedback(segment)
except Exception as e:
    print(f"   ⚠️ Feedback provider error: {e}", file=sys.stderr, flush=True)
    response = FeedbackResponse(action="skip")
```

---

### Fix 10: `has_pending_feedback` doesn't check `revision_requested`

**Files:** `aat/translate/feedback.py` (lines 33–39)
**Bug:** `revision_requested=True` is not considered pending feedback.

**Test (RED):** `tests/test_translate/test_feedback.py`
```
test_has_pending_with_revision_requested
  – Create segment with revision_requested=True, no comments/feedback.
    Assert has_pending_feedback() returns True.
```

**Fix (GREEN):** Add `or segment.revision_requested` to the return expression.

---

### Fix 11: `add_structured_feedback` return value not checked in server

**Files:** `aat/ui/server.py` (line 237)
**Bug:** Always redirects with "Feedback added" even if segment doesn't exist.

**Test (RED):** `tests/test_ui/test_revision.py`
```
test_structured_feedback_nonexistent_segment_returns_404
  – POST /segments/nonexistent/structured-feedback. Assert 404.
```

**Fix (GREEN):** Check return value:
```python
result = checkpoint_manager.add_structured_feedback(...)
if not result:
    raise HTTPException(status_code=404, detail="Segment not found")
```

---

## P2 – Major Fixes (9)

### Fix 12: `Checkpoint.from_json` doesn't handle `preferences: null`

**Files:** `aat/storage/checkpoints.py` (line 66)

**Test:** Assert `Checkpoint.from_json('{"project_id":"x","timestamp":"t","segment_states":{},"metadata":{},"preferences":null}')` returns `preferences == {}`.

**Fix:** `prefs = data.get("preferences"); preferences = prefs if isinstance(prefs, dict) else {}`

---

### Fix 13: `CheckpointPollingFeedbackProvider` timeout=0 may sleep

**Files:** `aat/translate/feedback.py` (lines 91, 118–122)

**Test:** Assert get_feedback with timeout=0 always completes in <50ms.

**Fix:** Short-circuit when `self._timeout <= 0`: do one check and return immediately without entering the polling loop.

---

### Fix 14: No input validation on `category` in structured-feedback endpoint

**Files:** `aat/ui/server.py` (line 227)

**Test:** POST with `category=INVALID_VALUE`. Assert 400 or normalized to OTHER.

**Fix:** Validate against allowed FeedbackCategory values; reject or normalize.

---

### Fix 15: `DraftTranslationPrompt` ignores non-terminology style preferences

**Files:** `aat/translate/prompts.py` (lines 149–250)

**Test:** Call build() with style_preferences={"tone": "academic"}. Assert "academic" appears in the prompt.

**Fix:** Add a `{style_preferences}` section to the template or append style info to the system prompt.

---

### Fix 16: `get_project_preferences` returns mutable reference

**Files:** `aat/storage/checkpoints.py` (line 237)

**Test:** Get preferences, mutate the returned dict, get again. Assert the second get is unaffected.

**Fix:** Return `dict(checkpoint.preferences)`.

---

### Fix 17: `preferences_page` inconsistent initialization check

**Files:** `aat/ui/server.py` (line 284)

**Test:** Call GET /preferences without create_app(). Assert 503.

**Fix:** Use `_check_initialized()` instead of manual `loader is None` check.

---

### Fix 18: No LLM error handling in revise endpoint

**Files:** `aat/ui/server.py` (line 270)

**Test:** Inject a client that raises LLMError. Assert endpoint returns 503 with message.

**Fix:** Wrap llm_client.chat() in try/except LLMError.

---

### Fix 19: `ProjectPreferences` and `StylePreference` defined but never used

**Files:** `aat/storage/models.py`

**Action:** Document that these are defined for future typed usage and that `Checkpoint.preferences` currently stores a plain dict. Add a `# TODO` or docstring note.

---

### Fix 20: `FeedbackResponse.action` has no type validation

**Files:** `aat/translate/feedback.py` (line 19)

**Fix:** Change type annotation to `Literal["approve", "revise", "skip"]` for static analysis. No runtime validation needed (pipeline `else` branch is safe).

---

## P3 – Minor/Nit (Deferred)

These items are real but low-impact. Fix opportunistically or in a dedicated polish pass.

| # | Issue | File(s) |
|---|-------|---------|
| 21 | CSRF protection on all POST forms | templates, server.py |
| 22 | Form labels and ARIA attributes in templates | all .html |
| 23 | `user_comments: list[dict]` should be `list[UserComment]` TypedDict | models.py |
| 24 | `critic_issues: list[dict]` should be typed | models.py |
| 25 | `time` import inside method → move to top | feedback.py |
| 26 | Missing `__all__` in feedback.py | feedback.py |
| 27 | `click` import lazy in InteractiveCLI → move to top or keep intentional | feedback.py |
| 28 | `load_latest_checkpoint` re-sorts by name vs mtime inconsistency | checkpoints.py |
| 29 | `set_project_preferences` replaces all prefs (no merge) — document | checkpoints.py |
| 30 | No input length limits on form data | server.py |
| 31 | `get_segment` is O(n) — could be O(1) | server.py |
| 32 | Global mutable state → use FastAPI DI | server.py |
| 33 | `_create_test_checkpoint` helper missing new fields | test_project_loader.py |
| 34 | Several UI tests only assert status code, not stored data | test_revision.py |
| 35 | `test_approve_nonexistent` accepts both 404 and 500 — tighten | test_server.py |
| 36 | `test_revise_not_initialized` patches globals unsafely | test_revision.py |
| 37 | "Needs Revision" badge missing in segments table | segments.html |
| 38 | Inline styles in preferences.html → shared CSS | preferences.html |
| 39 | `set-preference` with no options prints "Preferences saved" | cli.py |
| 40 | `revise --segment X` gives no message when X not found | cli.py |

---

## Execution Order

Fixes should be done in this order (dependencies flow downward):

```
Fix 1  (user_comments type)  ─┐
Fix 2  (user_feedback type)   ├─► Fix 3  (pass structured_feedback to _revise)
Fix 4  (polling provider)    ─┘
Fix 5  (FakeLLMClient)       ─── standalone
Fix 6  (--interactive)       ─── standalone
Fix 7  (RevisionPrompt term) ─── standalone
Fix 8  (reconstruct)         ─── standalone
Fix 9  (exception handling)  ─── standalone
Fix 10 (has_pending)         ─── standalone
Fix 11 (server 404)          ─── standalone
Fixes 12–20                  ─── independent, any order
```

**Estimated effort:** 2–3 focused sessions for P0+P1, 1 session for P2.
