# Option C Plan: Dogfood-Driven Translation Quality Improvements

> **Status:** Planning
> **Prerequisite:** Option A stabilization complete (391 tests green)
> **Estimated effort:** 3-4 focused sessions
> **References:** `specs/aat_translation_improvement_plan.md` iterations 3-4
> **Dogfood document:** Yuhan Lin 2018 dissertation
> **Venv:** `./venv/bin/python` (Python 3.13)
> **Test command:** `./venv/bin/python -m pytest tests/ -q --tb=short`

---

## Before You Start

1. Confirm all existing tests pass: `./venv/bin/python -m pytest tests/ -q --tb=short` -- expect 391+ passed, 0 failed
2. Confirm no API keys are needed: `unset ANTHROPIC_API_KEY && unset OPENAI_API_KEY` then re-run tests
3. Read these files to understand the current state:
   - `aat/translate/pipeline.py` -- the `_uncertainty_detect()` and `_revise()` methods you'll modify
   - `aat/translate/validators.py` -- `UncertaintyDetector` class (already implemented, needs wiring)
   - `aat/translate/prompts.py` -- `DraftTranslationPrompt` and `RevisionPrompt` (you'll add `notes` field)
   - `aat/translate/llm_client.py` -- `FakeLLMClient` (you'll update default response)
   - `aat/storage/models.py` -- `TranslationSegment`, `UncertaintyItem`, `PipelineConfig`

### What's Already Done (Option A / Iterations 1-2)

| Item | Status | What was built |
|------|--------|----------------|
| 1.1 Chapter-aware segmentation | Done | `ChapterDetector` class |
| 1.2 Metadata/YAML frontmatter | Done | CLI export with YAML |
| 1.3 Pre-translation planning | Done | `PlanningPrompt` class |
| 2.1 Terminology locking | Done | `TranslationMemory.lock_term()` |
| 2.2 Uncertainty detection (partial) | Done | `UncertaintyDetector` class exists but NOT wired into pipeline |
| 2.3 Revision loop (partial) | Done | `_revise()` calls `RevisionPrompt` via LLM, but single-pass only |
| Context assembly | Done | `ContextAssembler` wired into `_assemble_context()` |
| TM integration | Done | Locked terms fed into draft and revision prompts |

---

## Phase 1: Pipeline Quality Wiring (1 session)

### Step 1: Wire `UncertaintyDetector` into `_uncertainty_detect()`

File: `aat/translate/pipeline.py`

1. Add import at top: `from aat.translate.validators import UncertaintyDetector`

2. Add config field to `PipelineConfig`:
   ```python
   uncertainty_min_confidence: float = 0.6
   ```

3. In `__init__()`, after initializing `self.context_assembler`, add:
   ```python
   self.uncertainty_detector = UncertaintyDetector(
       min_confidence=self.config.uncertainty_min_confidence
   )
   ```

4. In `_uncertainty_detect()` method (currently at ~line 500), AFTER the existing LLM-reported uncertainty check and validator flag check, add:
   ```python
   # Run deterministic uncertainty detection on source text
   detected = self.uncertainty_detector.detect_all(segment.segment.source_text)
   for category, items in detected.items():
       for item in items:
           segment.uncertainties.append(
               UncertaintyItem(
                   type=item.get("type", category.upper()),
                   span=item.get("span", ""),
                   question=item.get("question", ""),
                   options=[],
               )
           )
   ```

5. The existing logic already routes to `USER_FEEDBACK_WAIT` if `_has_uncertainties()` returns True, so no state machine changes needed.

### Step 2: Implement multi-draft revision loop

File: `aat/translate/pipeline.py`

1. Add config field to `PipelineConfig`:
   ```python
   max_revision_rounds: int = 2
   ```

2. Add a revision counter to track rounds. In `_process_segment()`, before the `while not segment.locked:` loop, add:
   ```python
   revision_count = 0
   ```

3. In the `REVISE` state handler (inside the while loop), change:
   ```python
   elif segment.state.name == "REVISE":
       revision_count += 1
       # Store revision history
       if not segment.segment.metadata:
           segment.segment.metadata = {}
       history = segment.segment.metadata.get("revision_history", [])
       history.append({
           "round": revision_count,
           "draft": segment.translation,
           "issues": [str(r) for r in segment.validator_results if r.is_fail()],
       })
       segment.segment.metadata["revision_history"] = history

       if revision_count > self.config.max_revision_rounds:
           # Force-lock with warning
           segment.segment.metadata["force_locked"] = True
           segment.segment.metadata["force_lock_reason"] = (
               f"Max revision rounds ({self.config.max_revision_rounds}) exceeded"
           )
           segment.locked = True
           break

       self._revise(segment)
       segment.state = SegmentState.DETERMINISTIC_VALIDATE
   ```

### Step 3: Write tests for Phase 1

File: `tests/test_pipeline.py` -- add to the existing file.

1. **`TestUncertaintyDetectorWiring`** class (3 tests):
   - `test_ambiguous_pronoun_adds_uncertainty` -- source text "This suggests it is important" -> after `_uncertainty_detect()`, segment has uncertainties with span "it"
   - `test_clean_text_no_extra_uncertainties` -- source text "The value is 42." -> no new uncertainties added
   - `test_confidence_threshold_filters` -- create pipeline with `uncertainty_min_confidence=0.95`, source with ambiguous "it" (confidence 0.8) -> filtered out, no uncertainty added

2. **`TestMultiDraftRevision`** class (3 tests):
   - `test_revision_fixes_issue_in_round_1` -- use FakeLLMClient, segment with validator failure, after processing segment completes and is locked
   - `test_force_lock_after_max_rounds` -- set `max_revision_rounds=1`, use FakeLLMClient that always returns bad translation (missing citation), process segment -> segment.locked is True, `segment.segment.metadata["force_locked"]` is True
   - `test_revision_history_stored` -- process segment that goes through revision -> `segment.segment.metadata["revision_history"]` is a list with at least 1 entry containing "round" and "draft" keys

For `test_force_lock_after_max_rounds`: create a custom FakeLLMClient that always returns translations missing the citation, so validators always fail, forcing the revision loop to exhaust max rounds.

### Checkpoint 1

Run:
```bash
./venv/bin/python -m pytest tests/test_pipeline.py -q --tb=short
```

**Pass criteria:** All pipeline tests pass (existing 11 + new 6 = 17 tests).

Then run full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 397+ passed, 0 failed.

**Verify manually:** Add a temporary `print()` in `_uncertainty_detect()` to confirm the detector runs, then remove it.

---

## Phase 2: Quality Heuristics (1 session)

### Step 4: Create `aat/translate/quality.py`

Implement 4 heuristic classes, each with a `check(text: str) -> dict` method:

1. **`CalqueDetector`:**
   - Class attribute: `CALQUE_PATTERNS` -- list of regex patterns for common EN->ZH calques:
     - `r"在.*的光中"` (for "in light of")
     - `r"扮演.*角色"` (for "play a role" -- sometimes OK but flag it)
     - `r"在.*的末尾"` (for "at the end of")
     - `r"作为.*的结果"` (for "as a result of" -- sometimes OK)
     - Add 6-10 more common academic calque patterns
   - Method: `check(text: str) -> list[dict]` -- returns `[{"span": matched_text, "pattern": pattern_name, "confidence": float}]`

2. **`ReadabilityScorer`:**
   - Method: `check(text: str) -> dict` with keys:
     - `"score"`: 0-100 (100 = most readable)
     - `"long_sentences"`: list of sentences > 80 chars without Chinese punctuation (。！？；)
     - `"punctuation_density"`: ratio of punctuation chars to total chars
   - Score formula: `100 - (10 * num_long_sentences) - (20 if punctuation_density < 0.02 else 0)`
   - Clamp to 0-100

3. **`RepetitionDetector`:**
   - Method: `check(text: str) -> list[dict]` -- returns `[{"phrase": str, "count": int}]`
   - Split text into 4-char ngrams, count frequencies, flag any ngram appearing 3+ times
   - Ignore common Chinese function words (的, 了, 和, 是, 在, etc.)

4. **`AcademicToneChecker`:**
   - Class attribute: `INFORMAL_MARKERS` -- list of strings: `["了吧", "呢", "啊", "嘛", "哦", "哈", "呀", "吧", "嗯"]`
   - Method: `check(text: str) -> list[dict]` -- returns `[{"marker": str, "position": int}]`
   - Scan text for each marker, return positions found

5. **`run_quality_heuristics(text: str) -> dict`** -- convenience function:
   - Runs all 4 checkers
   - Returns `{"calques": [...], "readability": {...}, "repetitions": [...], "informal_markers": [...]}`

### Step 5: Wire quality heuristics into pipeline

File: `aat/translate/pipeline.py`

1. Add config field to `PipelineConfig`:
   ```python
   enable_quality_heuristics: bool = True
   ```

2. Add import: `from aat.translate.quality import run_quality_heuristics`

3. In `_llm_critic_review()`, AFTER the existing critic review logic, add:
   ```python
   # Run advisory quality heuristics
   if self.config.enable_quality_heuristics and segment.translation:
       if not segment.segment.metadata:
           segment.segment.metadata = {}
       segment.segment.metadata["quality_heuristics"] = run_quality_heuristics(
           segment.translation
       )
   ```

### Step 6: Create `tests/test_translate/test_quality.py`

Write these test classes:

1. **`TestCalqueDetector`** (3 tests):
   - `test_detects_known_calque` -- text "在这项研究的光中" -> flags 1 calque
   - `test_clean_text_no_calques` -- text "本研究旨在探讨" -> empty list
   - `test_multiple_calques` -- text with 2 calque patterns -> flags both

2. **`TestReadabilityScorer`** (3 tests):
   - `test_good_readability` -- short sentences with punctuation -> score >= 80
   - `test_long_sentence_flagged` -- single 100-char sentence with no punctuation -> score < 70, 1 long sentence flagged
   - `test_empty_text_returns_100` -- empty string -> score 100

3. **`TestRepetitionDetector`** (2 tests):
   - `test_repeated_phrase_flagged` -- "这是翻译这是翻译这是翻译这是翻译" -> flags "这是翻译"
   - `test_no_repetition` -- normal academic text -> empty list

4. **`TestAcademicToneChecker`** (2 tests):
   - `test_informal_markers_detected` -- text "这个结果很好啊" -> flags "啊"
   - `test_formal_text_passes` -- text "研究结果表明" -> empty list

5. **`TestRunQualityHeuristics`** (2 tests):
   - `test_returns_all_categories` -- output has keys "calques", "readability", "repetitions", "informal_markers"
   - `test_integration_with_real_text` -- run on a sample Chinese academic sentence -> no crash, returns valid structure

### Checkpoint 2

Run:
```bash
./venv/bin/python -m pytest tests/test_translate/test_quality.py -q --tb=short
```

**Pass criteria:** 12 tests pass, 0 failures.

Then run full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 409+ passed, 0 failed.

---

## Phase 3: Translation Notes + Quality Report (1 session)

### Step 7: Add translation notes to prompts and pipeline

1. **Update `aat/translate/prompts.py`:**
   - In `DraftTranslationPrompt.get_response_schema()`, add to the `properties`:
     ```python
     "notes": {
         "type": "array",
         "description": "翻译决策说明（非显而易见的翻译选择）",
         "items": {"type": "string"},
     }
     ```
   - Add `"notes"` to the `required` list
   - In `DraftTranslationPrompt.USER_TEMPLATE`, add to the JSON example:
     ```
     "notes": ["翻译决策说明1", "翻译决策说明2"]
     ```
   - Do the same for `RevisionPrompt.get_response_schema()` and `USER_TEMPLATE`

2. **Update `aat/translate/llm_client.py`:**
   - In `FakeLLMClient.chat()`, update the default JSON schema response:
     ```python
     return {
         "content": {
             "translation": "这是翻译文本。",
             "uncertainties": [],
             "notes": ["Test translation note"],
         }
     }
     ```

3. **Update `aat/translate/pipeline.py`:**
   - In `_draft_translate()`, after parsing `uncertainties_data`, add:
     ```python
     notes_data = content.get("notes", [])
     if isinstance(notes_data, list):
         segment.translation_notes = notes_data
     ```
   - In `_revise()`, after parsing the revised translation, add:
     ```python
     notes_data = content.get("notes", [])
     if isinstance(notes_data, list):
         segment.translation_notes.extend(notes_data)
     ```

4. **Verify `aat/storage/models.py`:** `TranslationSegment` already has `translation_notes: list[str]` field (added in Option A). If not, add it.

### Step 8: Create `aat/export/quality_report.py`

1. **`QualityReport` dataclass:**
   ```python
   @dataclass
   class QualityReport:
       source_document: str
       total_segments: int
       locked_segments: int
       chapters_detected: int
       planning_analyses: int
       revision_rounds: int
       avg_revisions_per_segment: float
       uncertainties_flagged: int
       uncertainties_unresolved: int
       citation_accuracy: float  # 0.0 - 1.0
       numeric_accuracy: float
       length_flags: int
       calque_suspects: int
       avg_readability: float
       repetition_flags: int
       informal_markers: int
       locked_terms: int
       tm_entries: int
       total_notes: int
       avg_notes_per_segment: float
   ```

2. **`generate_report(project: TranslationProject, tm: TranslationMemory | None = None) -> QualityReport`** function:
   - Count segments by state
   - Sum revision rounds from `segment.segment.metadata.get("revision_history", [])`
   - Count uncertainties across all segments
   - Count validator results by type (PASS/FAIL/FLAG)
   - Aggregate quality heuristic results from `segment.segment.metadata.get("quality_heuristics", {})`
   - Count translation notes across all segments
   - Count TM entries and locked terms if TM provided

3. **`QualityReport.to_text() -> str`** method:
   - Format the report as the plain-text block shown in the overview section
   - Use consistent alignment and section headers

4. **`QualityReport.to_dict() -> dict`** method:
   - Return `asdict(self)` (or manual dict construction)

### Step 9: Create `tests/test_export/__init__.py` and `tests/test_export/test_quality_report.py`

Write these tests:

1. **`TestGenerateReport`** (4 tests):
   - `test_report_from_completed_project` -- create project with 5 locked segments, known validator results, known quality heuristics in metadata -> verify all counts are correct
   - `test_report_from_empty_project` -- empty project -> all counts are 0, no crash
   - `test_report_counts_revision_rounds` -- 2 segments with revision_history of length 1 and 3 -> `revision_rounds == 4`
   - `test_report_includes_tm_stats` -- pass TM with 10 entries, 3 locked -> `locked_terms == 3`, `tm_entries == 10`

2. **`TestQualityReportFormat`** (3 tests):
   - `test_to_text_renders` -- call `.to_text()`, assert it contains "Translation Quality Report", "Total segments:", "Citation accuracy:"
   - `test_to_text_shows_percentages` -- report with `citation_accuracy=1.0` -> text contains "100"
   - `test_to_dict_roundtrip` -- `.to_dict()` returns dict with all expected keys, values match

### Step 10: Update `tests/test_pipeline.py` for translation notes

Add 2 tests to existing file:

1. **`test_draft_translate_stores_notes`** -- use FakeLLMClient (which now returns notes), call `_draft_translate()`, assert `segment.translation_notes` is not empty
2. **`test_draft_translate_handles_missing_notes`** -- use FakeLLMClient with custom response that has no "notes" key -> `segment.translation_notes` is empty list, no crash

### Checkpoint 3

Run full test suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 420+ passed (409 existing + ~11 new), 0 failed, no API keys.

**Verify:** Check that `FakeLLMClient` tests still pass (the default response changed to include notes -- make sure tests that check `response["content"]` still work with the new structure).

---

## Phase 4: Dogfood + Tuning (1 session)

### Step 11: Run pipeline on test data

1. Create a small test script `dogfood_quality.py` in the project root:
   ```python
   from aat.storage.models import *
   from aat.translate.pipeline import TranslationPipeline, PipelineConfig
   from aat.export.quality_report import generate_report

   # Create a small project with realistic academic text
   doc = DocumentModel.create()
   doc.sections = [Section(heading="Introduction", paragraphs=[
       Paragraph(pid="p1", text="This study examines stylistic variation (Smith, 2020)."),
       Paragraph(pid="p2", text="It suggests that they play a role in SDA acquisition."),
       Paragraph(pid="p3", text="The results show p < 0.05 was significant at that time."),
   ])]

   project = TranslationProject.create(doc)
   config = PipelineConfig(
       llm_provider="fake",
       enable_checkpoints=False,
       max_revision_rounds=2,
       uncertainty_min_confidence=0.6,
       enable_quality_heuristics=True,
   )
   pipeline = TranslationPipeline(project, config)
   result = pipeline.run()

   report = generate_report(result, pipeline.translation_memory)
   print(report.to_text())
   ```

2. Run it:
   ```bash
   ./venv/bin/python dogfood_quality.py
   ```

3. Verify output:
   - Report prints with non-zero counts
   - Uncertainties flagged for "it" and "they" (ambiguous pronouns)
   - Quality heuristics section shows results
   - Translation notes present

### Step 12: Tune thresholds

Based on dogfood results:
- If too many false positive uncertainties: raise `uncertainty_min_confidence` to 0.7 or 0.8
- If calque detector is too aggressive: remove or refine specific patterns
- If readability threshold too strict: adjust the 80-char sentence limit
- Update default values in `PipelineConfig` and `CalqueDetector.CALQUE_PATTERNS`

### Step 13: Compare with previous output

1. If `dissertation_full_translation_3.md` exists, compare:
   - Count uncertainty flags in new output vs old (old should be ~0, new should be >0)
   - Check if revision history appears in segments
   - Check if translation notes are populated

### Checkpoint 4 (Final)

**Pass criteria:**
1. Full test suite green: `./venv/bin/python -m pytest tests/ -q --tb=short` -- 420+ passed, 0 failed
2. `dogfood_quality.py` runs without errors, prints a valid quality report
3. Report shows non-zero values for: uncertainties_flagged, total_notes, calque_suspects or readability stats
4. No API keys needed

---

## Files to Create

| File | Purpose |
|------|---------|
| `aat/translate/quality.py` | CalqueDetector, ReadabilityScorer, RepetitionDetector, AcademicToneChecker, run_quality_heuristics() |
| `aat/export/quality_report.py` | QualityReport dataclass, generate_report() function |
| `tests/test_translate/test_quality.py` | Quality heuristic tests (12 tests) |
| `tests/test_export/__init__.py` | Test package |
| `tests/test_export/test_quality_report.py` | Report generation tests (7 tests) |

## Files to Modify

| File | Change |
|------|--------|
| `aat/translate/pipeline.py` | Wire UncertaintyDetector, multi-draft revision loop, quality heuristics, notes parsing. Add 3 fields to PipelineConfig. |
| `aat/translate/prompts.py` | Add `notes` field to DraftTranslationPrompt and RevisionPrompt schemas and templates |
| `aat/translate/llm_client.py` | Update FakeLLMClient default JSON response to include `notes` |
| `tests/test_pipeline.py` | Add 8 tests: 3 uncertainty wiring, 3 multi-draft revision, 2 translation notes |

---

## Relationship to Other Plans

- **Option B (M6)** handles global consistency pass and DOCX export -- no overlap
- **Option C** improves per-segment quality and adds observability
- Can be done before or after Option B; doing C first means B exports higher-quality translations
- Items 3.1 (DOCX output) and 3.3 (progress persistence) from the improvement plan are covered by Option B, not here
