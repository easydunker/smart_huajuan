# Option D Plan: Localhost Review UI

> **Status:** COMPLETE ✅ — All 4 phases done
> **Prerequisite:** Option A stabilization complete (391 tests green); ideally Option B or C done first
> **Estimated effort:** 4-5 focused sessions
> **PRD reference:** Section 3.2 (Localhost UI), Section 5.10 (User feedback & revision loop)
> **Approach:** FastAPI backend + Jinja2 server-rendered HTML templates, no JS build step
> **Venv:** `./venv/bin/python` (Python 3.13)
> **Test command:** `./venv/bin/python -m pytest tests/ -q --tb=short`

---

## Before You Start

1. Confirm all existing tests pass: `./venv/bin/python -m pytest tests/ -q --tb=short` -- expect 391+ passed, 0 failed
2. Confirm no API keys are needed: `unset ANTHROPIC_API_KEY && unset OPENAI_API_KEY` then re-run tests
3. Install new dependencies:
   ```bash
   ./venv/bin/pip install fastapi jinja2
   ```
4. Confirm uvicorn is available (should already be installed):
   ```bash
   ./venv/bin/python -c "import uvicorn; print(uvicorn.__version__)"
   ```
5. Read these files to understand checkpoint data structure:
   - `aat/storage/checkpoints.py` -- `Checkpoint`, `CheckpointManager` classes
   - `aat/storage/models.py` -- `TranslationSegment`, `SegmentState`, `UncertaintyItem`
   - `aat/cli.py` -- existing `--ui` flag placeholder
   - `checkpoints/` directory -- real checkpoint JSON files (if they exist)

### Architecture

```
aat translate paper.docx     (CLI, runs pipeline, saves checkpoints)
        |
        v
   checkpoints/*.json        (on-disk state)
        |
        v
aat review <project_dir>     (new CLI command, launches UI)
        |
        v
FastAPI server (localhost:8741)
        |
        +-- GET  /                    -> redirect to /segments
        +-- GET  /segments            -> paginated segment list
        +-- GET  /segments/{sid}      -> single segment detail view
        +-- POST /segments/{sid}/approve   -> lock segment
        +-- POST /segments/{sid}/comment   -> add user comment
        +-- POST /segments/{sid}/edit      -> edit translation text
        +-- POST /segments/{sid}/answer    -> answer uncertainty question
        +-- GET  /terminology         -> TM / termbank browser
        +-- GET  /api/status          -> JSON project status
```

---

## Phase 1: Backend + Project Loader (1 session) ✅ DONE

### Step 1: Add dependencies to `pyproject.toml`

Add to the `dependencies` list:
```toml
"fastapi>=0.110.0",
"jinja2>=3.1.0",
```

Run: `./venv/bin/pip install -e ".[dev]"` to install.

### Step 2: Create `aat/ui/__init__.py`

Empty file.

### Step 3: Add checkpoint write-back methods to `aat/storage/checkpoints.py`

Add these 4 methods to the `CheckpointManager` class:

1. **`update_segment(self, sid: str, updates: dict) -> bool`:**
   - Load latest checkpoint with `self.load_latest_checkpoint()`
   - If no checkpoint, return False
   - Find `sid` in `checkpoint.segment_states`
   - If not found, return False
   - Merge `updates` into `checkpoint.segment_states[sid]` (dict update)
   - Save back: `self.save_checkpoint(checkpoint)`
   - Return True

2. **`lock_segment(self, sid: str) -> bool`:**
   - Call `self.update_segment(sid, {"locked": True, "state": "lock_segment"})`

3. **`add_comment(self, sid: str, comment: str) -> bool`:**
   - Load latest checkpoint
   - Get segment state dict for `sid`
   - Get or create `"user_comments"` list in the segment state
   - Append `{"text": comment, "timestamp": datetime.now().isoformat()}`
   - Save back

4. **`update_translation(self, sid: str, new_translation: str) -> bool`:**
   - Call `self.update_segment(sid, {"translation": new_translation})`

### Step 4: Create `aat/ui/server.py`

1. **`ProjectLoader` class:**
   ```python
   class ProjectLoader:
       def __init__(self, project_dir: Path):
           self.checkpoint_manager = CheckpointManager(project_dir)
           self._checkpoint = None
           self.reload()

       def reload(self):
           self._checkpoint = self.checkpoint_manager.load_latest_checkpoint()

       def get_segments(self) -> list[dict]:
           """Return all segments as dicts with sid, source, translation, state, locked, etc."""
           if not self._checkpoint:
               return []
           segments = []
           for sid, state_data in self._checkpoint.segment_states.items():
               if isinstance(state_data, dict):
                   segments.append({
                       "sid": sid,
                       "source_text": state_data.get("segment", {}).get("source_text", ""),
                       "translation": state_data.get("translation", ""),
                       "state": state_data.get("state", "unknown"),
                       "locked": state_data.get("locked", False),
                       "uncertainties": state_data.get("uncertainties", []),
                       "validator_results": state_data.get("validator_results", []),
                       "critic_issues": state_data.get("critic_issues", []),
                       "user_comments": state_data.get("user_comments", []),
                       "chapter_id": state_data.get("segment", {}).get("metadata", {}).get("chapter_id", "unknown"),
                   })
           return segments

       def get_segment(self, sid: str) -> dict | None:
           """Return single segment by ID."""
           for seg in self.get_segments():
               if seg["sid"] == sid:
                   return seg
           return None

       def list_segments(self, page: int = 1, per_page: int = 50, state_filter: str | None = None) -> tuple[list[dict], int]:
           """Return paginated segment list and total count."""
           segments = self.get_segments()
           if state_filter == "locked":
               segments = [s for s in segments if s["locked"]]
           elif state_filter == "needs_review":
               segments = [s for s in segments if not s["locked"] and not s["uncertainties"]]
           elif state_filter == "uncertain":
               segments = [s for s in segments if s["uncertainties"]]
           total = len(segments)
           start = (page - 1) * per_page
           return segments[start:start + per_page], total

       def get_stats(self) -> dict:
           """Return project statistics."""
           segments = self.get_segments()
           return {
               "total": len(segments),
               "locked": sum(1 for s in segments if s["locked"]),
               "unlocked": sum(1 for s in segments if not s["locked"]),
               "uncertain": sum(1 for s in segments if s["uncertainties"]),
               "project_id": self._checkpoint.project_id if self._checkpoint else "unknown",
               "timestamp": self._checkpoint.timestamp if self._checkpoint else "unknown",
           }
   ```

2. **FastAPI app setup:**
   ```python
   from fastapi import FastAPI, Request, Form, HTTPException
   from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
   from fastapi.templating import Jinja2Templates

   app = FastAPI(title="AAT Review UI")
   templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

   # Global state -- set by create_app()
   loader: ProjectLoader | None = None
   checkpoint_manager: CheckpointManager | None = None

   def create_app(project_dir: Path) -> FastAPI:
       global loader, checkpoint_manager
       checkpoint_manager = CheckpointManager(project_dir)
       loader = ProjectLoader(project_dir)
       return app
   ```

3. **Routes to implement in this phase:**
   - `GET /` -- redirect to `/segments`
   - `GET /api/status` -- return `loader.get_stats()` as JSON

### Step 5: Create `tests/test_ui/__init__.py`

Empty file.

### Step 6: Create `tests/test_ui/test_project_loader.py`

Write these tests (all create checkpoint data in `tmp_path`):

1. **Helper function:** `_create_test_checkpoint(tmp_path, segments_data)` that:
   - Creates `tmp_path / "checkpoints"` directory
   - Writes a `checkpoint_*.json` file with given segment data
   - Returns the `tmp_path`

2. **`TestProjectLoader`** (5 tests):
   - `test_load_from_checkpoint` -- create checkpoint with 3 segments, load -> `len(get_segments()) == 3`
   - `test_get_segment_by_sid` -- create checkpoint, `get_segment("s1")` returns correct source_text and translation
   - `test_get_segment_not_found` -- `get_segment("nonexistent")` returns None
   - `test_list_segments_pagination` -- 10 segments, `list_segments(page=1, per_page=5)` returns 5 segments and total=10
   - `test_get_stats` -- 3 segments (2 locked, 1 unlocked with uncertainty) -> stats show correct counts

3. **`TestCheckpointWriteBack`** (4 tests):
   - `test_lock_segment` -- create checkpoint, `lock_segment("s1")`, reload -> segment is locked
   - `test_add_comment` -- `add_comment("s1", "test comment")`, reload -> comment exists with timestamp
   - `test_update_translation` -- `update_translation("s1", "new text")`, reload -> translation changed
   - `test_update_nonexistent_segment` -- `update_segment("bad_id", {})` returns False

### Checkpoint 1

Run:
```bash
./venv/bin/python -m pytest tests/test_ui/test_project_loader.py -q --tb=short
```

**Pass criteria:** 9 tests pass, 0 failures.

Then run full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 400+ passed, 0 failed.

**Result:** 477 passed (463 original + 14 new), 1 skipped, 0 failed. ✅

---

## Phase 2: Segment List + CLI Command (1 session) ✅ DONE

### Step 7: Create `aat/ui/templates/base.html`

Jinja2 base template with:
- `<!DOCTYPE html>`, charset utf-8
- `<style>` block with clean CSS:
  - Sans-serif font (system font stack)
  - Max-width 1200px centered container
  - Table styling with alternating row colors
  - Badge styles: `.badge-locked` (green), `.badge-review` (yellow), `.badge-fail` (red), `.badge-uncertain` (blue)
  - Navigation bar with links: Segments | Terminology
  - Responsive layout
- `{% block title %}{% endblock %}` in `<title>`
- `{% block content %}{% endblock %}` in `<body>`

### Step 8: Create `aat/ui/templates/segments.html`

Extends `base.html`. Content:

1. **Summary bar:**
   ```html
   <div class="summary">
     {{ stats.locked }}/{{ stats.total }} segments locked,
     {{ stats.unlocked }} need review,
     {{ stats.uncertain }} have uncertainties
   </div>
   ```

2. **Filter buttons:**
   ```html
   <div class="filters">
     <a href="/segments">All</a>
     <a href="/segments?filter=locked">Locked</a>
     <a href="/segments?filter=needs_review">Needs Review</a>
     <a href="/segments?filter=uncertain">Uncertain</a>
   </div>
   ```

3. **Table:**
   - Headers: # | Chapter | Source Preview | Translation Preview | State | Actions
   - For each segment: show first 80 chars of source/translation, state badge, link to `/segments/{{ seg.sid }}`

4. **Pagination:**
   - Show page links if total > per_page

### Step 9: Add segment list route to `aat/ui/server.py`

```python
@app.get("/segments", response_class=HTMLResponse)
async def segment_list(request: Request, page: int = 1, filter: str | None = None):
    segments, total = loader.list_segments(page=page, state_filter=filter)
    stats = loader.get_stats()
    return templates.TemplateResponse("segments.html", {
        "request": request,
        "segments": segments,
        "stats": stats,
        "page": page,
        "total": total,
        "per_page": 50,
        "filter": filter,
    })
```

### Step 10: Add `aat review` CLI command to `aat/cli.py`

1. Add new command after the existing commands:
   ```python
   @main.command()
   @click.argument("project_folder", type=click.Path(exists=True))
   @click.option("--port", default=8741, help="Port for review UI server")
   def review(project_folder: str, port: int) -> None:
       """Launch review UI for a translation project."""
       from pathlib import Path
       from aat.ui.server import create_app
       import uvicorn
       import webbrowser

       project_dir = Path(project_folder)
       app = create_app(project_dir)

       url = f"http://127.0.0.1:{port}"
       click.echo(f"Review UI running at {url}")
       click.echo("Press Ctrl+C to stop")

       webbrowser.open(url)
       uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
   ```

2. Update the `--ui` flag handler in the `translate` command (line ~54):
   ```python
   if ui:
       click.echo("After translation completes, run: aat review <project_dir>")
   ```

### Step 11: Create `tests/test_ui/test_server.py` (GET routes only for now)

Use FastAPI `TestClient` (no real server needed):

```python
from fastapi.testclient import TestClient
```

1. **Fixture:** `client` -- create a test checkpoint in `tmp_path`, call `create_app(tmp_path)`, return `TestClient(app)`

2. **Tests (4 tests):**
   - `test_root_redirects_to_segments` -- `GET /` returns 307 redirect to `/segments`
   - `test_segments_page_returns_html` -- `GET /segments` returns 200, response contains "segments" and the segment table
   - `test_segments_filter_locked` -- `GET /segments?filter=locked` returns 200, only locked segments shown
   - `test_api_status_returns_json` -- `GET /api/status` returns 200, JSON body has "total", "locked", "unlocked" keys

### Step 12: Add CLI test for `review` command

File: `tests/test_cli.py` -- add:

1. `test_review_requires_folder` -- `aat review` with no args -> exit code != 0
2. `test_review_nonexistent_folder` -- `aat review /nonexistent` -> exit code != 0

(Don't test actual server start -- that would block. Just test argument validation.)

### Checkpoint 2

Run:
```bash
./venv/bin/python -m pytest tests/test_ui/ -q --tb=short
```

**Pass criteria:** 13 tests pass (9 from phase 1 + 4 new).

Then full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 406+ passed, 0 failed.

**Result:** 483 passed, 1 skipped, 0 failed. ✅

**Manual check:** Start the server manually and verify in browser:
```bash
# Only if you have real checkpoint data in checkpoints/
./venv/bin/python -c "
from aat.ui.server import create_app
import uvicorn
app = create_app('checkpoints')
uvicorn.run(app, host='127.0.0.1', port=8741)
"
```
Open http://127.0.0.1:8741/segments -- should show segment table. If no checkpoints, show empty state.

---

## Phase 3: Segment Detail View + Actions (1.5 sessions) ✅ DONE

### Step 13: Create `aat/ui/templates/segment_detail.html`

Extends `base.html`. Layout sections (top to bottom):

1. **Navigation:** `<< Prev | Segment {index}/{total} | Next >>`
   - Prev/Next link to adjacent segment SIDs

2. **Side-by-side panels (use CSS grid or flexbox):**
   - Left: "Source (EN)" heading + `<pre>` or `<div>` with source_text
   - Right: "Translation (ZH)" heading + translation text + Edit button
   - If segment is locked, show green "Locked" badge, disable edit

3. **Edit form (hidden by default, shown on Edit click):**
   ```html
   <form method="POST" action="/segments/{{ seg.sid }}/edit">
     <textarea name="translation">{{ seg.translation }}</textarea>
     <button type="submit">Save</button>
     <button type="button" onclick="cancel()">Cancel</button>
   </form>
   ```

4. **Validator Results panel:**
   - For each result in `seg.validator_results`:
     - Show badge: PASS (green), FAIL (red), FLAG (yellow)
     - Show validator name and detail text

5. **Critic Issues panel:**
   - For each issue in `seg.critic_issues`:
     - Show `issue.code` and `issue.detail`

6. **Uncertainties panel (if any):**
   - For each uncertainty:
     - Show question text
     - If options provided, show radio buttons for each option
     - Text input for custom answer
     - Submit button -> POST to `/segments/{sid}/answer`

7. **Comments panel:**
   - Show existing comments with timestamps
   - Add comment form:
     ```html
     <form method="POST" action="/segments/{{ seg.sid }}/comment">
       <input name="comment" placeholder="Add comment..." />
       <button type="submit">Submit</button>
     </form>
     ```

8. **Action buttons:**
   - "Approve & Lock" button -> POST to `/segments/{sid}/approve` (disabled if already locked)
   - "Request Revision" button (placeholder for future -- just a disabled button with tooltip)

### Step 14: Add detail + POST routes to `aat/ui/server.py`

1. **`GET /segments/{sid}`:**
   ```python
   @app.get("/segments/{sid}", response_class=HTMLResponse)
   async def segment_detail(request: Request, sid: str):
       segment = loader.get_segment(sid)
       if not segment:
           raise HTTPException(status_code=404, detail="Segment not found")
       # Find prev/next SIDs
       all_segments = loader.get_segments()
       sids = [s["sid"] for s in all_segments]
       idx = sids.index(sid) if sid in sids else -1
       prev_sid = sids[idx - 1] if idx > 0 else None
       next_sid = sids[idx + 1] if idx < len(sids) - 1 else None
       return templates.TemplateResponse("segment_detail.html", {
           "request": request,
           "seg": segment,
           "index": idx + 1,
           "total": len(sids),
           "prev_sid": prev_sid,
           "next_sid": next_sid,
       })
   ```

2. **`POST /segments/{sid}/approve`:**
   - Call `checkpoint_manager.lock_segment(sid)`
   - Call `loader.reload()`
   - Find next unlocked segment SID
   - Redirect to next unlocked segment, or back to `/segments` if none left

3. **`POST /segments/{sid}/comment`:**
   - Read `comment` from form data
   - Call `checkpoint_manager.add_comment(sid, comment)`
   - Call `loader.reload()`
   - Redirect back to `/segments/{sid}`

4. **`POST /segments/{sid}/edit`:**
   - Read `translation` from form data
   - Call `checkpoint_manager.update_translation(sid, translation)`
   - Call `loader.reload()`
   - Redirect back to `/segments/{sid}`

5. **`POST /segments/{sid}/answer`:**
   - Read answer from form data
   - Store answer in segment metadata via `checkpoint_manager.update_segment(sid, {"uncertainty_answers": {question: answer}})`
   - Clear the answered uncertainty
   - Call `loader.reload()`
   - Redirect back to `/segments/{sid}`

### Step 15: Add POST route tests to `tests/test_ui/test_server.py`

Add these tests (6 tests):

1. `test_segment_detail_returns_html` -- `GET /segments/s1` returns 200, contains source text and translation
2. `test_segment_detail_not_found` -- `GET /segments/nonexistent` returns 404
3. `test_approve_locks_segment` -- `POST /segments/s1/approve` returns redirect, reload checkpoint -> segment locked
4. `test_add_comment` -- `POST /segments/s1/comment` with form data `comment=test` -> redirect, comment stored
5. `test_edit_translation` -- `POST /segments/s1/edit` with form data `translation=新翻译` -> redirect, translation updated
6. `test_approve_already_locked` -- `POST` approve on locked segment -> should still succeed (idempotent)

### Checkpoint 3

Run full suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 418+ passed, 0 failed.

**Result:** 490 passed, 1 skipped, 0 failed. ✅

**Manual check:** Start server, navigate to a segment detail page, and test each action:
1. Click Edit, change text, save -- verify text changed on reload
2. Add a comment -- verify it appears with timestamp
3. Click Approve -- verify segment shows as locked, redirects to next unlocked
4. Navigate with Prev/Next buttons

---

## Phase 4: Terminology Browser + Polish (0.5 session) ✅ DONE

### Step 16: Create `aat/ui/templates/terminology.html`

Extends `base.html`. Content:

1. **Search bar:**
   ```html
   <input type="text" id="search" placeholder="Search terms..." onkeyup="filterTable()">
   ```

2. **Table:**
   - Headers: Source Term | Target Term | Locked | Confidence | Chapter
   - For each TM entry (or termbank item), show row with locked badge (green/grey)

3. **Vanilla JS filter function:**
   ```javascript
   function filterTable() {
     const query = document.getElementById('search').value.toLowerCase();
     const rows = document.querySelectorAll('table tbody tr');
     rows.forEach(row => {
       const text = row.textContent.toLowerCase();
       row.style.display = text.includes(query) ? '' : 'none';
     });
   }
   ```

### Step 17: Add terminology route to `aat/ui/server.py`

```python
@app.get("/terminology", response_class=HTMLResponse)
async def terminology(request: Request):
    # Load TM data from checkpoint metadata or separate TM file
    segments = loader.get_segments()
    # Extract unique terms from segment metadata
    terms = []  # Build from segment planning_analysis or grounding data
    return templates.TemplateResponse("terminology.html", {
        "request": request,
        "terms": terms,
    })
```

### Step 18: Polish the UI

1. **Keyboard shortcuts** (add to `base.html`):
   ```javascript
   document.addEventListener('keydown', function(e) {
     if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
     if (e.key === 'j' && document.querySelector('.next-link')) {
       window.location = document.querySelector('.next-link').href;
     }
     if (e.key === 'k' && document.querySelector('.prev-link')) {
       window.location = document.querySelector('.prev-link').href;
     }
   });
   ```

2. **Toast notifications:** After POST actions, add a query parameter `?msg=saved` and show a brief notification div at the top of the page.

3. **Responsive layout:** Ensure side-by-side panels stack vertically on narrow screens (`@media (max-width: 768px)`).

### Checkpoint 4 (Final)

Run full test suite:
```bash
./venv/bin/python -m pytest tests/ -q --tb=short
```

**Pass criteria:** 420+ passed, 0 failed, no API keys needed.

**Result:** 491 passed, 1 skipped, 0 failed. ✅

**Manual full workflow test:**
1. Create test data:
   ```bash
   ./venv/bin/python -c "
   from aat.storage.models import *
   from aat.translate.pipeline import TranslationPipeline, PipelineConfig
   from aat.storage.checkpoints import CheckpointManager, Checkpoint
   from pathlib import Path
   import tempfile

   doc = DocumentModel.create()
   doc.title = 'Test Document'
   doc.sections = [Section(heading='Introduction', paragraphs=[
       Paragraph(pid='p1', text='This is a test (Smith, 2020).'),
       Paragraph(pid='p2', text='It suggests p < 0.05 is significant.'),
   ])]
   project = TranslationProject.create(doc)
   config = PipelineConfig(llm_provider='fake', enable_checkpoints=False)
   pipeline = TranslationPipeline(project, config)
   result = pipeline.run()

   test_dir = Path('test_review_project')
   test_dir.mkdir(exist_ok=True)
   cm = CheckpointManager(test_dir)
   cm.save_checkpoint(Checkpoint.create(result))
   print(f'Checkpoint saved to {test_dir}')
   "
   ```

2. Start review UI:
   ```bash
   ./venv/bin/python -m aat review test_review_project
   ```

3. In browser at http://127.0.0.1:8741:
   - Segment list shows all segments with correct states
   - Click a segment -- detail view shows EN/ZH side by side
   - Edit a translation, save -- text updates
   - Add a comment -- comment appears with timestamp
   - Approve a segment -- badge changes to green, redirects to next
   - Check terminology page -- shows terms if available
   - Use j/k keys to navigate between segments

4. Clean up: `rm -rf test_review_project`

---

## Files to Create

| File | Purpose |
|------|---------|
| `aat/ui/__init__.py` | Package init |
| `aat/ui/server.py` | FastAPI app, routes, ProjectLoader |
| `aat/ui/templates/base.html` | Base template with layout, nav, CSS |
| `aat/ui/templates/segments.html` | Segment list / dashboard |
| `aat/ui/templates/segment_detail.html` | Single segment review view |
| `aat/ui/templates/terminology.html` | TM / termbank browser |
| `tests/test_ui/__init__.py` | Test package |
| `tests/test_ui/test_server.py` | FastAPI route tests (10 tests) |
| `tests/test_ui/test_project_loader.py` | ProjectLoader + write-back tests (9 tests) |

## Files to Modify

| File | Change |
|------|--------|
| `aat/cli.py` | Add `aat review` command, update `--ui` flag message |
| `aat/storage/checkpoints.py` | Add 4 write-back methods: `update_segment()`, `lock_segment()`, `add_comment()`, `update_translation()` |
| `pyproject.toml` | Add `fastapi>=0.110.0`, `jinja2>=3.1.0` to dependencies |
| `tests/test_cli.py` | Add 2 tests for `aat review` argument validation |

---

## Relationship to Other Plans

- **Option B (M6):** M6 adds DOCX export and global pass. The UI could show global pass results, but that's additive -- not a dependency.
- **Option C (Quality):** Quality heuristics and translation notes would appear in the segment detail view. If C is done first, the UI shows richer data. If not, those panels are simply empty.
- **Option D does NOT depend on B or C.** It reads whatever checkpoint data exists.
