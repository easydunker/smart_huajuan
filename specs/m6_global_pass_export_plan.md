# M6 Plan: Global Consistency Pass + DOCX Export

> **Status:** Planning
> **Prerequisite:** M1-M5 complete, Option A stabilization done (391 tests green)
> **Estimated effort:** 3-4 focused sessions
> **PRD reference:** Section 5.11, Milestone M6
> **Venv:** `./venv/bin/python` (Python 3.13)
> **Test command:** `./venv/bin/python -m pytest tests/ -q --tb=short`

---

## Before You Start

1. Confirm all existing tests pass: `./venv/bin/python -m pytest tests/ -q --tb=short` -- expect 391+ passed, 0 failed
2. Confirm no API keys are needed: `unset ANTHROPIC_API_KEY && unset OPENAI_API_KEY` then re-run tests
3. Read these files to understand the current state:
   - `aat/export/chapter.py` -- existing chapter-level export (JSON only)
   - `aat/translate/validators.py` -- `CitationPreservationValidator` patterns (reuse for global check)
   - `aat/translate/translation_memory.py` -- `TranslationMemory` with locked terms
   - `aat/storage/models.py` -- `TranslationProject`, `TranslationSegment` dataclasses
   - `aat/cli.py` -- the `export` and `status` command stubs

---

## Phase 1: Global Consistency Pass (1 session)

### Step 1: Create `aat/export/global_pass.py`

1. Create the file with these classes:

2. **`TermInconsistency` dataclass:**
   - Fields: `source_term: str`, `translations: dict[str, list[str]]` (Chinese translation -> list of segment IDs), `suggested: str`

3. **`CitationIssue` dataclass:**
   - Fields: `citation: str`, `issue_type: str` ("DROPPED" or "INJECTED"), `segment_ids: list[str]`

4. **`GlobalPassReport` dataclass:**
   - Fields: `term_inconsistencies: list[TermInconsistency]`, `citation_issues: list[CitationIssue]`, `passed: bool`, `summary: str`

5. **`TermConsistencyChecker` class:**
   - Method `check(segments: list[TranslationSegment], tm: TranslationMemory) -> list[TermInconsistency]`
   - For each segment, extract English terms from source using regex `r'\b[A-Z][a-z]+(?:\s+[a-z]+){0,3}\b'` (capitalized noun phrases)
   - Search for each term across all translated segments
   - If the same English term maps to 2+ different Chinese strings -> create `TermInconsistency`
   - Skip terms that are in TM locked entries (those are intentionally consistent)

6. **`CitationConsistencyChecker` class:**
   - Method `check(segments: list[TranslationSegment]) -> list[CitationIssue]`
   - Reuse patterns from `CitationPreservationValidator` (`PARENTHETICAL_PATTERN`, `BRACKETED_PATTERN`, etc.)
   - Collect all citations from all source segments into `source_citations: set`
   - Collect all citations from all translated segments into `translation_citations: set`
   - Any citation in source but not in translation -> `CitationIssue(type="DROPPED")`
   - Any citation in translation but not in source -> `CitationIssue(type="INJECTED")`

7. **`GlobalPassOrchestrator` class:**
   - Method `run(project: TranslationProject, tm: TranslationMemory) -> GlobalPassReport`
   - Run `TermConsistencyChecker.check()` and `CitationConsistencyChecker.check()`
   - Set `passed = True` only if both return empty lists
   - Generate `summary` string: "Global pass: X term inconsistencies, Y citation issues"

### Step 2: Create `tests/test_milestone6/__init__.py`

Empty file.

### Step 3: Create `tests/test_milestone6/test_global_pass.py`

Write these test classes:

1. **`TestTermConsistencyChecker`** (4 tests):
   - `test_consistent_terms_pass` -- all segments translate "Machine Learning" as "机器学习" -> empty list
   - `test_inconsistent_terms_flagged` -- seg1 translates "deep learning" as "深度学习", seg2 as "深层学习" -> 1 inconsistency
   - `test_locked_tm_terms_not_flagged` -- same scenario but term is locked in TM -> empty list
   - `test_no_segments_returns_empty` -- empty segment list -> empty list

2. **`TestCitationConsistencyChecker`** (3 tests):
   - `test_all_citations_preserved` -- source has "(Smith, 2020)", translation has it too -> empty list
   - `test_dropped_citation_reported` -- source has "(Smith, 2020)", translation missing it -> 1 issue with type "DROPPED"
   - `test_injected_citation_reported` -- translation has "(Fake, 2099)" not in source -> 1 issue with type "INJECTED"

3. **`TestGlobalPassOrchestrator`** (3 tests):
   - `test_clean_project_passes` -- no issues -> `report.passed is True`
   - `test_inconsistent_project_fails` -- has term inconsistency -> `report.passed is False`, `len(report.term_inconsistencies) > 0`
   - `test_report_summary_contains_counts` -- summary string includes issue counts

All tests must use `FakeLLMClient` and create `TranslationProject` / `TranslationSegment` objects directly (no real LLM calls).

### Checkpoint 1

Run:
```bash
./venv/bin/python -m pytest tests/test_milestone6/test_global_pass.py -q --tb=short
```

**Pass criteria:** 10 tests pass, 0 failures. Then run full suite to confirm no regressions:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```
**Pass criteria:** 401+ passed (391 existing + 10 new), 0 failed.

---

## Phase 2: DOCX Export (1 session)

### Step 4: Create `aat/export/docx_export.py`

1. **`DocxExporter` class:**
   - Constructor: `__init__(self, project: TranslationProject, report: GlobalPassReport | None = None)`
   - Method: `export(output_path: Path, bilingual: bool = False) -> Path`

2. **`export()` implementation steps:**
   - Create `docx.Document()` using `python-docx`
   - Call `_add_metadata_page()` as first content
   - Group segments by `chapter_id` from `segment.segment.metadata.get("chapter_id", "unknown")`
   - For each chapter group:
     - Add `Heading 1` with chapter name
     - For each segment in the chapter:
       - If `bilingual=True`: add source paragraph with italic style, then translation paragraph with normal style
       - If `bilingual=False`: add only translation paragraph
   - Save document to `output_path`

3. **`_add_metadata_page()` method:**
   - Add title: "Translation: {project.document.title}"
   - Add paragraph: "Translated: {datetime.now()}"
   - Add paragraph: "Total segments: {len(project.segments)}"
   - Add paragraph: "Locked segments: {count of locked}"
   - If `report` provided: add paragraph: "Global pass: {'PASSED' if report.passed else 'ISSUES FOUND'}"
   - Add page break

4. **`_add_references_section()` method:**
   - If `project.document.references` is not empty, add "References" heading and list each reference

### Step 5: Create `tests/test_milestone6/test_docx_export.py`

Write these tests (all use `tmp_path` fixture for output):

1. **`TestDocxExporter`** (6 tests):
   - `test_export_creates_docx_file` -- export to tmp_path, assert file exists and is > 0 bytes
   - `test_export_contains_translations` -- export, re-read with `python-docx`, assert translated text is present
   - `test_export_has_chapter_headings` -- create segments with chapter_id metadata, export, verify headings in docx
   - `test_export_preserves_citations` -- segment with "(Smith, 2020)" in translation, verify it's in the exported docx text
   - `test_bilingual_mode_has_source_and_translation` -- export with `bilingual=True`, verify both English and Chinese text present
   - `test_metadata_page_present` -- export, verify first paragraph contains "Translation:" and segment count

Create test helper: `_make_project(segments_data: list[dict]) -> TranslationProject` that builds a project with given segments (source_text, translation, chapter_id, locked=True).

### Checkpoint 2

Run:
```bash
./venv/bin/python -m pytest tests/test_milestone6/test_docx_export.py -q --tb=short
```

**Pass criteria:** 6 tests pass. Then run full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```
**Pass criteria:** 407+ passed, 0 failed.

**Manual check:** Open one of the generated `.docx` files from `tmp_path` (print the path in a test with `print(output_path)`) and verify it looks reasonable in a text editor or Word.

---

## Phase 3: CLI + Integration (1 session)

### Step 6: Wire `aat export` for full project in `aat/cli.py`

1. In the `export()` function, replace the `else` branch (line ~431 "Full project export not yet implemented") with:
   - Add `--bilingual` flag to the `@click.option` decorators
   - Add `--skip-global-pass` flag
   - Load checkpoint: `CheckpointManager(project_dir).load_latest_checkpoint()`
   - If no checkpoint found, print error and abort
   - Reconstruct `TranslationProject` from checkpoint data (create a helper `_project_from_checkpoint(checkpoint)` function)
   - If not `skip_global_pass`: run `GlobalPassOrchestrator`, print report to stderr
   - Call `DocxExporter(project, report).export(output_path, bilingual=bilingual)`
   - Print success message with output path

2. The `_project_from_checkpoint(checkpoint)` helper:
   - Create `DocumentModel` with title from `checkpoint.metadata["title"]`
   - Create `TranslationSegment` for each entry in `checkpoint.segment_states`
   - Return `TranslationProject` with segments populated

### Step 7: Implement `aat status` in `aat/cli.py`

1. Replace the stub in `status()` (line ~452) with:
   - Accept optional `project_folder` argument (default: current directory)
   - Load latest checkpoint via `CheckpointManager`
   - If no checkpoint, print "No project found" and return
   - Count: total segments, locked, unlocked, with uncertainties
   - Group by `chapter_id` from segment metadata
   - Use `rich.table.Table` to display:
     - Header row: Project ID, last checkpoint time
     - Table: Chapter | Total | Locked | Unlocked | % Complete
     - Footer row: totals

### Step 8: Create `tests/test_milestone6/test_export_integration.py`

End-to-end integration test (3 tests):

1. **`test_full_pipeline_to_docx`:**
   - Create `TranslationProject` with fake document (2 sections, 4 paragraphs)
   - Create `PipelineConfig(llm_provider="fake", enable_checkpoints=False)`
   - Run `TranslationPipeline(project, config).run()`
   - Assert all segments locked
   - Run `GlobalPassOrchestrator` -> get report
   - Export with `DocxExporter` -> assert `.docx` file exists
   - Re-read `.docx` with python-docx -> assert contains translated text

2. **`test_export_with_empty_project`:**
   - Project with no segments -> export should produce a docx with just the metadata page, no crash

3. **`test_bilingual_export_integration`:**
   - Same as test 1 but with `bilingual=True` -> verify both EN and ZH in output

### Step 9: Update `tests/test_cli.py`

Add these tests (all mocked):

1. **`test_export_docx_format`** -- mock `CheckpointManager` to return a checkpoint, mock `DocxExporter`, run `aat export <dir> --format docx`, assert exit code 0
2. **`test_export_bilingual`** -- same but with `--bilingual` flag
3. **`test_status_with_checkpoint`** -- mock `CheckpointManager`, run `aat status`, assert output contains "Project" and segment counts
4. **`test_status_no_checkpoint`** -- mock `CheckpointManager` to return None, assert appropriate message

### Checkpoint 3

Run full test suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 420+ passed, 0 failed, no API keys set.

**Manual check:** Run these commands and verify output:
```bash
# Should show help with new flags
./venv/bin/python -m aat export --help
# Should show --bilingual and --skip-global-pass options
```

---

## Phase 4: Polish (0.5 session)

### Step 10: Dogfood with real data

1. Check if `checkpoints/` folder has real checkpoint data:
   ```bash
   ls checkpoints/
   ```
2. If checkpoints exist, run:
   ```bash
   ./venv/bin/python -m aat export checkpoints/ --format docx -o test_output.docx
   ```
3. Open `test_output.docx` and verify:
   - Title page is present with metadata
   - Chapters have headings
   - Translations are readable Chinese
   - Citations like "(Smith, 2020)" are intact
   - No garbled text or encoding issues

4. Run bilingual export:
   ```bash
   ./venv/bin/python -m aat export checkpoints/ --format docx --bilingual -o test_bilingual.docx
   ```
5. Verify bilingual output has interleaved EN/ZH paragraphs

### Step 11: Fix edge cases

Common issues to check:
- Segments with `None` translation (unlocked segments) -- should be skipped or show placeholder
- Segments with no `chapter_id` -- should fall into "Unknown Chapter" group
- Very long segments -- should not break DOCX formatting
- Unicode characters in translations -- should export correctly

### Checkpoint 4 (Final)

**Pass criteria:**
1. Full test suite green: `./venv/bin/python -m pytest tests/ -q --tb=short` -- 420+ passed, 0 failed
2. `test_output.docx` opens correctly in Word/Pages/LibreOffice
3. `test_bilingual.docx` shows interleaved EN/ZH
4. No API keys needed for any test

---

## Files to Create

| File | Purpose |
|------|---------|
| `aat/export/global_pass.py` | TermConsistencyChecker, CitationConsistencyChecker, GlobalPassOrchestrator |
| `aat/export/docx_export.py` | DocxExporter with bilingual mode and metadata |
| `tests/test_milestone6/__init__.py` | Test package |
| `tests/test_milestone6/test_global_pass.py` | Global pass tests (10 tests) |
| `tests/test_milestone6/test_docx_export.py` | DOCX export tests (6 tests) |
| `tests/test_milestone6/test_export_integration.py` | End-to-end integration test (3 tests) |

## Files to Modify

| File | Change |
|------|--------|
| `aat/cli.py` | Wire full export (replace stub), implement status, add --bilingual/--skip-global-pass flags |
| `aat/export/__init__.py` | Export new modules |
| `tests/test_cli.py` | Add 4 tests for new CLI features |
