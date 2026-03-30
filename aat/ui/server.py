"""FastAPI server for the AAT Review UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aat.storage.checkpoints import CheckpointManager
from aat.translate.llm_client import FakeLLMClient
from aat.translate.prompts import RevisionPrompt


class ProjectLoader:
    """Loads and queries checkpoint data for the review UI."""

    def __init__(self, project_dir: Path) -> None:
        self.checkpoint_manager = CheckpointManager(project_dir)
        self._checkpoint = None
        self.reload()

    def reload(self) -> None:
        self._checkpoint = self.checkpoint_manager.load_latest_checkpoint()

    def get_segments(self) -> list[dict]:
        """Return all segments as dicts with sid, source, translation, state, etc."""
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
                    "structured_feedback": state_data.get("structured_feedback", []),
                    "revision_requested": state_data.get("revision_requested", False),
                    "chapter_id": (
                        state_data.get("segment", {})
                        .get("metadata", {})
                        .get("chapter_id", "unknown")
                    ),
                })
        return segments

    def get_segment(self, sid: str) -> dict | None:
        """Return single segment by ID."""
        for seg in self.get_segments():
            if seg["sid"] == sid:
                return seg
        return None

    def list_segments(
        self,
        page: int = 1,
        per_page: int = 50,
        state_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return paginated segment list and total count."""
        segments = self.get_segments()
        if state_filter == "locked":
            segments = [s for s in segments if s["locked"]]
        elif state_filter == "needs_review":
            segments = [s for s in segments if not s["locked"] and not s["uncertainties"]]
        elif state_filter == "uncertain":
            segments = [s for s in segments if s["uncertainties"]]
        elif state_filter == "needs_revision":
            segments = [s for s in segments if s.get("revision_requested") or s.get("structured_feedback")]
        total = len(segments)
        page = max(1, page)
        per_page = max(1, per_page)
        start = (page - 1) * per_page
        return segments[start : start + per_page], total

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


# -- FastAPI app -----------------------------------------------------------

app = FastAPI(title="AAT Review UI")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

loader: ProjectLoader | None = None
checkpoint_manager: CheckpointManager | None = None


def create_app(project_dir: Path) -> FastAPI:
    """Initialize global state and return the FastAPI app."""
    global loader, checkpoint_manager  # noqa: PLW0603
    checkpoint_manager = CheckpointManager(project_dir)
    loader = ProjectLoader(project_dir)
    return app


@app.get("/")
async def root():
    return RedirectResponse(url="/segments")


@app.get("/segments", response_class=HTMLResponse)
async def segment_list(
    request: Request,
    page: int = 1,
    filter: str | None = None,  # noqa: A002
):
    if loader is None:
        return HTMLResponse("<h1>Not initialized</h1><p>Run create_app() first.</p>", status_code=503)
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


@app.get("/segments/{sid}", response_class=HTMLResponse)
async def segment_detail(request: Request, sid: str):
    if loader is None:
        return HTMLResponse("Not initialized", status_code=503)
    segment = loader.get_segment(sid)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
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


def _check_initialized():
    if loader is None or checkpoint_manager is None:
        raise HTTPException(status_code=503, detail="Not initialized")


@app.post("/segments/{sid}/approve")
async def approve_segment(sid: str):
    _check_initialized()
    result = checkpoint_manager.lock_segment(sid)
    if not result:
        raise HTTPException(status_code=404, detail="Segment not found")
    loader.reload()
    all_segments = loader.get_segments()
    next_unlocked = next((s["sid"] for s in all_segments if not s["locked"]), None)
    target = f"/segments/{next_unlocked}?msg=Segment+approved" if next_unlocked else "/segments?msg=All+segments+locked"
    return RedirectResponse(url=target, status_code=303)


@app.post("/segments/{sid}/comment")
async def add_comment(sid: str, comment: str = Form(...)):
    _check_initialized()
    result = checkpoint_manager.add_comment(sid, comment)
    if not result:
        raise HTTPException(status_code=404, detail="Segment not found")
    loader.reload()
    return RedirectResponse(url=f"/segments/{sid}?msg=Comment+added", status_code=303)


@app.post("/segments/{sid}/edit")
async def edit_translation(sid: str, translation: str = Form(...)):
    _check_initialized()
    seg = loader.get_segment(sid)
    if seg and seg.get("locked"):
        raise HTTPException(status_code=409, detail="Cannot edit locked segment")
    result = checkpoint_manager.update_translation(sid, translation)
    if not result:
        raise HTTPException(status_code=404, detail="Segment not found")
    loader.reload()
    return RedirectResponse(url=f"/segments/{sid}?msg=Translation+saved", status_code=303)


@app.post("/segments/{sid}/answer")
async def answer_uncertainty(
    sid: str,
    question: str = Form(...),
    answer: str = Form(""),
    custom_answer: str = Form(""),
):
    _check_initialized()
    final_answer = custom_answer if answer == "__custom__" and custom_answer else (answer or custom_answer)
    if final_answer:
        checkpoint = checkpoint_manager.load_latest_checkpoint()
        if checkpoint and sid in checkpoint.segment_states:
            seg = checkpoint.segment_states[sid]
            answers = seg.get("uncertainty_answers", {})
            answers[question] = final_answer
            seg["uncertainty_answers"] = answers
            uncertainties = seg.get("uncertainties", [])
            seg["uncertainties"] = [u for u in uncertainties if u.get("question") != question]
            checkpoint_manager.save_checkpoint(checkpoint)
            loader.reload()
    return RedirectResponse(url=f"/segments/{sid}?msg=Answer+saved", status_code=303)


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


@app.post("/segments/{sid}/revise")
async def revise_segment(sid: str):
    _check_initialized()
    seg = loader.get_segment(sid)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    comments = []
    for c in seg.get("user_comments", []):
        if isinstance(c, dict):
            comments.append(c.get("text", ""))
        elif isinstance(c, str):
            comments.append(c)

    structured = seg.get("structured_feedback", [])
    prefs = checkpoint_manager.get_project_preferences()

    llm_client = FakeLLMClient()
    messages = RevisionPrompt.build(
        source_text=seg["source_text"],
        current_translation=seg["translation"],
        critic_issues=seg.get("critic_issues", []),
        user_feedback=comments,
        user_answers={},
        structured_feedback=structured,
        style_preferences=prefs,
    )
    schema = RevisionPrompt.get_response_schema()
    response = llm_client.chat(messages, json_schema=schema)

    content = response.get("content", {})
    if isinstance(content, dict):
        new_translation = content.get("translation", "")
        if new_translation:
            checkpoint_manager.update_translation(sid, new_translation)
            checkpoint_manager.update_segment(sid, {"revision_requested": False})

    loader.reload()
    return RedirectResponse(url=f"/segments/{sid}?msg=Revision+complete", status_code=303)


@app.get("/preferences", response_class=HTMLResponse)
async def preferences_page(request: Request):
    if loader is None:
        return HTMLResponse("Not initialized", status_code=503)
    prefs = checkpoint_manager.get_project_preferences()
    term_overrides = prefs.get("terminology_overrides", {})
    style = {k: v for k, v in prefs.items() if k != "terminology_overrides"}
    return templates.TemplateResponse("preferences.html", {
        "request": request,
        "term_overrides": term_overrides,
        "style": style,
    })


@app.post("/preferences")
async def save_preferences(
    formality: str = Form(""),
    tone: str = Form(""),
):
    _check_initialized()
    prefs = checkpoint_manager.get_project_preferences()
    if formality:
        prefs["formality"] = formality
    if tone:
        prefs["tone"] = tone
    checkpoint_manager.set_project_preferences(prefs)
    return RedirectResponse(url="/preferences?msg=Preferences+saved", status_code=303)


@app.post("/preferences/term")
async def add_term_override(
    source: str = Form(...),
    target: str = Form(...),
):
    _check_initialized()
    prefs = checkpoint_manager.get_project_preferences()
    overrides = prefs.get("terminology_overrides", {})
    overrides[source] = target
    prefs["terminology_overrides"] = overrides
    checkpoint_manager.set_project_preferences(prefs)
    return RedirectResponse(url="/preferences?msg=Term+added", status_code=303)


@app.post("/preferences/term/delete")
async def delete_term_override(source: str = Form(...)):
    _check_initialized()
    prefs = checkpoint_manager.get_project_preferences()
    overrides = prefs.get("terminology_overrides", {})
    overrides.pop(source, None)
    prefs["terminology_overrides"] = overrides
    checkpoint_manager.set_project_preferences(prefs)
    return RedirectResponse(url="/preferences?msg=Term+removed", status_code=303)


@app.get("/terminology", response_class=HTMLResponse)
async def terminology(request: Request):
    if loader is None:
        return HTMLResponse("Not initialized", status_code=503)
    terms = _extract_terms(loader)
    return templates.TemplateResponse("terminology.html", {
        "request": request,
        "terms": terms,
    })


def _extract_terms(ldr: ProjectLoader) -> list[dict]:
    """Extract term-like data from segment metadata or grounding info."""
    if not ldr._checkpoint:
        return []
    terms = []
    seen = set()
    for sid, state_data in ldr._checkpoint.segment_states.items():
        if not isinstance(state_data, dict):
            continue
        chapter = state_data.get("segment", {}).get("metadata", {}).get("chapter_id", "")
        planning = state_data.get("planning_analysis", {})
        if isinstance(planning, dict):
            for term_entry in planning.get("key_terms", []):
                if isinstance(term_entry, dict):
                    src = term_entry.get("source", term_entry.get("term", ""))
                    tgt = term_entry.get("target", term_entry.get("translation", ""))
                    if src and (src, tgt) not in seen:
                        seen.add((src, tgt))
                        terms.append({
                            "source": src,
                            "target": tgt,
                            "confidence": term_entry.get("confidence", 0.0),
                            "chapter": chapter,
                        })
    return terms


@app.get("/api/status")
async def api_status():
    if loader is None:
        return JSONResponse({"error": "not initialized"}, status_code=503)
    return JSONResponse(loader.get_stats())
