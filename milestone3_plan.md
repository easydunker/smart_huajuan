# Milestone 3: Checkpointing + Resume + Chapter Export

## Overview
Implement segment-level checkpointing, resume logic, and chapter-based export functionality.

## Components to Implement

### 1. Checkpointing (aat/storage/checkpoints.py)
**Required Operations:**
- `save_checkpoint(segment, checkpoint_data)` - Save checkpoint to JSON file
- `load_latest_checkpoint()` - Load most recent checkpoint from project folder
- `list_checkpoints()` - List all checkpoint files (sorted newest first)
- `cleanup_old_checkpoints(keep_count=10)` - Keep only N most recent

**Schema:**
```json
{
  "sid": "segment_id",
  "source_hash": "sha256(source_text)",
  "translation": "string|None",
  "state": "DRAFT_TRANSLATE|REVIEWING|LOCKED",
  "validator_results": [...],
  "critic_issues": [...],
  "uncertainties": [...],
  "user_comments": "string|None",
  "timestamp": "ISO8601",
  "metadata": {...}
}
```

### 2. Resume Command Logic (CLI Integration)
**Command:** `aat resume <project_folder>`

**Behavior:**
- Continue from first unlocked segment (not reprocess locked segments)
- Do NOT reprocess locked segments
- Skip already-completed segments
- For segments without checkpoint: start at DRAFT_TRANSLATE
- For segments with checkpoints: resume from checkpoint state

**State Machine:**
```
DRAFT_TRANSLATE → VALIDATING → REVIEWING → LOCKED
```

**Required for Milestone 3 (per spec):**
- Support checkpoint persistence per segment
- Resume command that processes state transitions correctly
- Fail gracefully when checkpoint file is corrupted

### 3. Chapter Export
**Command:** `aat export <project_folder> --chapter <chapter_id>`

**Behavior:**
- Export only approved segments belonging to specified chapter
- Preserve chapter structure (headings in order)
- If some segments in chapter are unapproved, warn and export only approved content
- Do NOT silently include unapproved segments

**Required for Milestone 3 (per spec):**
- `chapter_id` parameter selects which chapter to export
- Chapter structure preservation
- Approval state handling for segments

## Files to Create

1. `aat/storage/checkpoints.py` - Update CheckpointManager for persistence
2. `aat/cli.py` - Add `resume` command integration
3. `aat/export/chapter.py` - New module for chapter export
4. `tests/test_milestone3/` - New test directory for Milestone 3 tests

## Files to Modify

1. No modifications to existing modules (Milestone 2 components remain unchanged)

## Implementation Order

### Phase 1: CheckpointManager Enhancement
1. Add checkpoint file creation (JSON per segment)
2. Add `load_latest_checkpoint()` method
3. Add `list_checkpoints()` method
4. Add `cleanup_old_checkpoints()` method
5. Add error handling for corrupted checkpoints

### Phase 2: Resume Command Integration
1. Add `resume` command to CLI
2. Ensure it reads project metadata (project_id, etc.)
3. Integrate with CheckpointManager

### Phase 3: Chapter Export
1. Create `aat/export/chapter.py` module
2. Implement `export_chapter(project_id)` function
3. Integrate with existing storage models

### Phase 4: Tests
1. Create `tests/test_milestone3/` directory
2. Add unit tests for CheckpointManager
3. Add integration tests for `resume` command
4. Add unit tests for chapter export
5. Mock LLM calls where needed (use FakeLLMClient)

## Tests Requirements

### CheckpointManager Tests
- Save checkpoint creates valid JSON file
- Load checkpoint reads JSON file correctly
- List checkpoints returns sorted list (newest first)
- Cleanup keeps N most recent
- Graceful error handling on corrupted files

### Resume Command Tests
- `aat resume` creates CheckpointManager and processes segments
- Continues from first unlocked segment
- Does not reprocess locked segments
- Skips already-completed segments
- Handles interruption and resumption

### Chapter Export Tests
- `aat export --chapter <id>` exports only approved segments
- Preserves chapter structure (headings + paragraph order)
- Warns on unapproved segments (doesn't export them)
- Does NOT silently include unapproved segments

## Coverage Requirements

- New/modified files must have >= 90% coverage
- All existing passing tests must maintain coverage
- Overall repository coverage target: 85% (may not be achievable due to Python 3.13.7 system bug)

## Stop Criteria

Milestone is complete when:
1. File tree of new/modified files provided
2. List of implemented modules
3. List of tests added
4. Commands executed
5. Tests pass (green test suite for new/modified files with >=90% coverage)
6. Coverage report for new/modified files
7. Full test suite results (acknowledge legacy failures)
8. Statement: "Milestone 3 complete, did not implement Milestone 4+ features"
