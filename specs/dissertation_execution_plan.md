---

# 📘 Dissertation Execution Plan

## Local Academic Translation Agent (EN → ZH)

### Addendum to academic_translator_prd.md

---

# 0. Purpose

This document defines the **strict milestone-based implementation plan** for supporting **very long dissertations (200–800+ pages)**.

This file is execution-oriented and overrides any ambiguous behavior in the main PRD for long-document handling.

Claude Code + Ralph Loop must follow this plan incrementally.

---

# 1. Global Rules for Implementation

1. Implement milestone-by-milestone.
2. Write tests for each milestone before moving forward.
3. Do not implement UI or retrieval until core scalability works.
4. If ambiguity occurs → STOP and ask.
5. Do not translate entire dissertation in one prompt.
6. Must support resume from checkpoint at any time.
7. Must pass coverage thresholds before proceeding.

---

# 2. High-Level Dissertation Architecture

Dissertation support is implemented in 4 stages:

```
M1: Structure Mapping + Scalable Parsing
M2: Segmentation + Translation Memory (TM)
M3: Checkpointing + Resume + Export by Chapter
M4: Hierarchical Translation Loop + Consistency Enforcement
```

UI and retrieval are NOT part of the dissertation milestone sequence.

---

# 3. Milestone 1 — Structure Mapping & Scalable Parsing

## Objective

Build a scalable parsing layer that can handle 500+ page DOCX without high memory usage.

---

## 3.1 Required Components

### A) DissertationParser

* Parses DOCX incrementally.
* Extracts:

  * Chapters (detect by heading styles)
  * Sections
  * Paragraphs
* Does NOT load full document text into memory as one string.

### B) DocumentMap Builder

Generate:

```json
{
  "doc_id": "...",
  "chapters": [
    {
      "chapter_id": "...",
      "title": "...",
      "section_ids": [...]
    }
  ],
  "paragraph_index": {
    "pid": {
      "chapter_id": "...",
      "section_id": "...",
      "text_hash": "..."
    }
  }
}
```

### C) Memory Constraint Rule

* Maximum memory spike allowed: document size × 2.
* No full-text concatenation allowed.

---

## 3.2 Required Tests

### A) Large Synthetic DOCX Test

Generate synthetic DOCX (~200+ pages).
Test:

* Parser completes.
* DocumentMap generated.
* No memory explosion.

### B) Chapter Boundary Test

* Ensure headings become chapter boundaries.
* Ensure nested sections preserved.

### C) Text Integrity Test

* Concatenating all parsed paragraphs equals original document text (ignoring formatting).

---

## 3.3 Exit Criteria for M1

* All tests pass.
* Coverage ≥ 90% for parsing module.
* Can parse 300-page synthetic doc without crash.

---

# 4. Milestone 2 — Segmentation + Translation Memory (TM)

## Objective

Create scalable segmentation and global consistency storage.

---

## 4.1 Required Components

### A) Segmenter (Chapter-aware)

* Segment within chapter boundaries only.
* Segment size: 200–400 tokens.
* Must not:

  * Split inside citation
  * Split inside sentence
* Preserve paragraph IDs.

### B) Translation Memory Store (TM)

Schema:

```json
{
  "source_phrase": "...",
  "normalized_key": "...",
  "target_phrase": "...",
  "first_used_chapter": "...",
  "locked": true/false,
  "confidence": 0.0
}
```

Stored in SQLite.

### C) TM Retrieval

Before translating a segment:

* Retrieve top matching phrases via:

  * exact match
  * embedding similarity (optional later)
* Inject into translation context.

---

## 4.2 Required Tests

### A) Segmentation Invariant Test

* Segments concatenated == original text.
* No empty segments.
* No split inside citation pattern.

### B) TM Lock Test

* If user locks term:

  * Future segments must use identical translation.

### C) Cross-Chapter Consistency Test

* Same phrase in chapter 1 and 5
* TM ensures same translation.

---

## 4.3 Exit Criteria for M2

* All segmentation tests pass.
* TM enforces consistency.
* Coverage ≥ 90% for segmenter + TM modules.

---

# 5. Milestone 3 — Checkpointing + Resume + Chapter Export

## Objective

Make dissertation processing crash-safe and resumable.

---

## 5.1 Required Components

### A) CheckpointManager

For each segment:

Store:

* source hash
* translation versions
* validator outputs
* approval status
* model metadata
* timestamp

### B) Resume Command

```
aat resume <project>
```

Behavior:

* Continue from first unlocked segment.
* Do NOT redo approved segments.

### C) Chapter Export

```
aat export <project> --chapter <id>
```

Exports only approved segments for that chapter.

---

## 5.2 Required Tests

### A) Simulated Crash Test

* Process first 10 segments.
* Kill pipeline.
* Resume.
* Ensure:

  * No duplication
  * No re-translation of locked segments

### B) Partial Export Test

* Only approved segments exported.
* Structure preserved.

### C) Checkpoint Integrity Test

* Corrupted checkpoint detected gracefully.

---

## 5.3 Exit Criteria for M3

* Resume works.
* No re-translation of locked segments.
* Chapter export works.
* Coverage ≥ 90% for checkpoint manager.

---

# 6. Milestone 4 — Hierarchical Translation Loop

## Objective

Add scalable context management for long documents.

---

## 6.1 Required Components

### A) Global Style Guide Generator

Run once:

* Generate Chinese academic style constraints.
* Save as `global_style.json`.

### B) Chapter Summary Generator

After each chapter:

* Generate ≤ 200-token summary in Chinese.
* Store for future context.

### C) Context Assembler (Hierarchical)

For each segment:

Context includes:

1. Global style guide
2. Global termbank
3. Chapter summary
4. Previous segment translation (or summary)
5. TM locked phrases

Must enforce context token limit.

---

## 6.2 Required Tests

### A) Context Size Test

* Context never exceeds model token limit.
* Fails safely if exceeded.

### B) Summary Propagation Test

* Chapter 2 translation uses summary from Chapter 1.

### C) Consistency Enforcement Test

* TM + hierarchical context prevent drift across 5+ chapters.

---

## 6.3 Exit Criteria for M4

* Hierarchical translation works.
* No attempt to translate full dissertation in one prompt.
* Consistency maintained across chapters.

---

# 7. Dissertation Performance Requirements

* Must handle 500-page DOCX without crash.
* Must allow resume after interruption.
* Must allow exporting by chapter.
* Must prevent numeric and citation hallucination at segment level.

---

# 8. Forbidden Behaviors

* Do not use entire dissertation as prompt.
* Do not rely on ultra-long context models.
* Do not bypass checkpointing.
* Do not skip validators for speed.

---

# 9. Completion Criteria

Dissertation support is considered complete when:

* Large synthetic dissertation passes full pipeline.
* Resume works.
* TM ensures cross-chapter consistency.
* Chapter export works.
* All tests green.
* Coverage thresholds satisfied.

---

# 10. Implementation Order (Strict)

1. M1 Parsing & Structure
2. M2 Segmentation + TM
3. M3 Checkpoint + Resume
4. M4 Hierarchical Translation Loop
5. THEN retrieval & UI improvements

Do not reorder.

---

---


