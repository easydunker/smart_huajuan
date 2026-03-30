---

# PRD — Local Academic Translation Agent (EN→ZH), Reference-Aware, Free Search by Default

## 0) One-sentence summary

Build a local-first CLI + localhost UI app that translates academic documents from English to Chinese using (a) reference-aware grounding from free academic sources and user-provided PDFs, (b) segment-by-segment translation + review + deterministic anti-hallucination checks, and (c) user-in-the-loop comments and clarification questions; only paid component may be LLM API calls.

---

## 1) Product constraints (non-negotiable)

### 1.1 Local-first

* Runs locally on macOS/Linux (Windows optional later).
* Stores all outputs/checkpoints locally.
* Works in **offline mode** (no network calls).

### 1.2 External search behavior

* Default external search must be **free** (no paid APIs required).
* External search is **opt-in**: user must enable explicitly (`--enable-web`).
* CNKI (中国知网): **no automated scraping**, no bypassing paywalls.

  * Support manual import: user can add CNKI PDFs they legally downloaded.

### 1.3 Paid components

* The only paid component allowed is **LLM API calls** (optional).
* App must support **local models** (Ollama) as a free alternative.

---

## 2) Target users & use cases

* Academic researchers translating papers, proposals, theses from EN → ZH.
* Need accurate terminology, faithful meaning, and publication tone.

Core use cases:

1. Translate a DOCX paper with citations and references.
2. Ask user questions when ambiguous.
3. Let user comment per segment and revise.
4. Ground translation terminology using Chinese academic writing from free sources or user library.

---

## 3) Deliverables

### 3.1 CLI

Binary name: `aat` (Academic AI Translator)

Commands:

* `aat translate <input_path> --to zh [--enable-web] [--offline] [--ui]`
* `aat add-library <file_or_folder>`
* `aat resume <project_folder>`
* `aat export <project_folder> --format docx`

### 3.2 Localhost UI (MVP-simple)

* Runs at `http://127.0.0.1:PORT`
* Segment viewer:

  * left: source English
  * right: translated Chinese
  * below: validator + critic reports
  * comment box + approve button
  * “answer questions” panel for UNCERTAIN items

### 3.3 Local storage

* SQLite for metadata + versions
* Filesystem for text chunks/checkpoints
* Vector DB (Chroma or FAISS) stored locally

---

## 4) Supported input/output

### Input (MVP)

* `.docx` only (PDF later)

### Output (MVP)

* Translated `.docx` preserving:

  * headings
  * paragraphs
  * citations (exact text)
  * reference list (translated conservatively)

---

## 5) Functional requirements

## 5.1 Document parsing

Implement `DocxParser`:

* Extract:

  * full text with structure (sections/paragraphs)
  * reference section boundaries (heuristic)
  * in-text citations (patterns: `(Author, 2020)`, `[12]`, `Smith et al., 2021`)
* Output canonical `DocumentModel`.

### DocumentModel schema

```json
{
  "doc_id": "uuid",
  "title": "string|null",
  "sections": [
    {
      "heading": "string|null",
      "paragraphs": [{"pid":"string","text":"string"}]
    }
  ],
  "references": [{"rid":"string","raw":"string"}],
  "citations": [{"cid":"string","text":"string","pid":"string"}]
}
```

---

## 5.2 Reference-aware retrieval (free-by-default)

### Retrieval sources (MVP)

1. **User local library** (PDF/DOCX added via `aat add-library`)
2. **OpenAlex** (free) when `--enable-web` is on

Do NOT implement:

* automated Google Scholar scraping in MVP
* automated CNKI scraping ever

### Retrieval goal

Build a **Chinese phrasebank + termbank** from:

* Chinese papers related to the references and topic keywords

### OpenAlex integration

* Query by:

  * reference title if parseable
  * otherwise keywords from abstract/introduction
* Prefer results with:

  * Chinese language or Chinese venues
  * Chinese abstracts (if available)

Store retrieved metadata and any text snippets you can legally access.

---

## 5.3 Local library ingestion

Implement `LibraryIngestor`:

* Accept PDFs and DOCX
* Extract text (PDF via `pypdf` or `pdfminer.six`; no OCR in MVP)
* Chunk into ~300 tokens
* Embed locally using a local embedding model (recommend: `bge-m3` or a multilingual embedding model)
* Store in local vector DB with metadata:

  * file path
  * chunk id
  * source type (local/openalex)
  * language guess

---

## 5.4 Phrasebank & termbank builder

Implement `GroundingBuilder`:

Outputs:

### TermBank

```json
{
  "items":[
    {
      "source_term":"string",
      "target_term":"string",
      "examples":[{"source":"string","quote":"string"}],
      "confidence":0.0
    }
  ]
}
```

### PhraseBank

```json
{
  "functions":{
    "introduce_contribution":["本文提出…","本研究旨在…"],
    "describe_method":["我们采用…方法","本文使用…进行分析"],
    "state_results":["结果表明…","研究发现…"]
  }
}
```

How to build:

* Use retrieval results as corpus
* Extract frequent academic patterns
* Extract bilingual terminology candidates via:

  * LLM (preferred)
  * OR simple heuristic alignment (fallback)

---

## 5.5 Segmentation

Implement `Segmenter`:

* Produces segments of 200–400 tokens.
* Must not split:

  * inside a citation
  * mid-sentence
* Each segment keeps pointer to original paragraph ids.

Segment schema:

```json
{
  "sid":"string",
  "pid_list":["p1","p2"],
  "source_text":"string",
  "context_before":"string|null"
}
```

---

## 5.6 Translation pipeline (per segment)

### State machine for each segment

1. `assemble_context`
2. `draft_translate`
3. `deterministic_validate`
4. `llm_critic_review`
5. `uncertainty_detect`
6. `user_feedback_wait`
7. `revise`
8. `lock_segment`

### LLM draft translation requirements

Hard constraints:

* Do not add new citations
* Preserve citation text EXACTLY (character-for-character)
* Preserve numbers EXACTLY
* Academic Chinese tone
* Use termbank + phrasebank

LLM output format (strict JSON):

```json
{
  "translation":"string",
  "uncertainties":[
    {"type":"TERM","span":"...","question":"...","options":["...","..."]}
  ]
}
```

---

## 5.7 Deterministic anti-hallucination validators (must-have)

Implement validators that run without LLM:

1. **CitationPreservationValidator**

* Extract citations from source and translation using regex
* Must match exactly (order-insensitive acceptable, but content exact)

2. **NumericFidelityValidator**

* Extract numbers, percentages, ranges
* Must match exactly

3. **ReferenceInjectionValidator**

* If translation contains any citation pattern not in source → FAIL

4. **LengthChangeHeuristic**

* If translation length > 1.6× source length → flag (not fail)

Validator output:

```json
{
  "status":"PASS|FAIL|FLAG",
  "issues":[{"code":"CITATION_MISMATCH","detail":"..."}]
}
```

---

## 5.8 LLM critic review

Use a second call:

* Inputs: source_text + translation + termbank
* Outputs issues list:

  * meaning drift
  * omission
  * addition
  * term inconsistency
* Must be structured JSON.

---

## 5.9 Uncertainty handling

Rules:

* If any `uncertainties` exist OR any validator FAIL occurs → must require user action.
* UI/CLI must prompt user:

  * answer uncertainty question
  * or manually edit translation
  * or approve with explicit override flag `--force`

---

## 5.10 User feedback & revision loop

Per segment:

* user can comment
* user can edit translation
* user can answer questions
  Then system runs `revise`:
* incorporate user comment + answers
* re-run validators
* if pass → lock

Store full version history.

---

## 5.11 Final assembly + global pass

After all segments locked:

* concatenate translations in original order
* run global checks:

  * term consistency (same term translated consistently)
  * citation consistency
* export DOCX

---

## 6) Configuration

Config file at:
`~/.aat/config.toml`

Example:

```toml
model_provider = "ollama" # or "openai"
model_name = "qwen2.5:14b"
enable_web_default = false
embedding_model = "bge-m3"
vector_store = "chroma"
```

---

## 7) Model provider abstraction

Implement interface:

```python
class LLMClient:
    def chat(self, messages: list[dict], json_schema: dict, **kwargs) -> dict: ...
```

Implement providers:

* `OllamaClient` (free)
* `OpenAIClient` (paid)

---

## 8) Repo structure (required)

```
aat/
  cli.py
  server.py
  orchestrator/
    graph.py
    state.py
  parsing/
    docx_parser.py
    citation.py
  retrieval/
    openalex.py
    library_ingest.py
    vector_store.py
  grounding/
    termbank.py
    phrasebank.py
    build.py
  translate/
    prompts.py
    pipeline.py
    validators.py
    critic.py
  storage/
    db.py
    models.py
    checkpoints.py
  export/
    docx_export.py
  ui/
    (minimal react or server-rendered templates)
tests/
  test_validators.py
  test_segmenter.py
  test_docx_roundtrip.py
```

---

## 9) Acceptance tests (MVP)

1. **Citation preservation**

* Input with citations `(Smith, 2021)` → output must contain exact `(Smith, 2021)`

2. **Numeric fidelity**

* “p < 0.05” remains exactly “p < 0.05”

3. **Segment review loop**

* When uncertainty exists, pipeline pauses until user responds.

4. **Offline mode**

* `--offline` makes zero network calls (add a network guard that errors if attempted).

5. **Web enabled mode**

* `--enable-web` performs OpenAlex retrieval and stores cached results.

6. **Export**

* Output docx preserves paragraph order and headings.

---

## 10) Explicit “don’t do” list

* Do not scrape CNKI.
* Do not bypass paywalls.
* Do not require paid search APIs.
* Do not execute arbitrary shell commands from model output.
* Do not silently continue when validator fails (must block or require explicit override).

---

## 11) Milestones (engineering)

M1: CLI + DOCX parse + segmentation
M2: translation draft + validators + checkpoints
M3: localhost UI + comment loop
M4: library ingest + embeddings + vector DB
M5: OpenAlex retrieval + phrasebank/termbank
M6: global pass + docx export polish

---

## 12) Open questions (for future, not blocking MVP)

* PDF OCR support
* Google Scholar opt-in connector
* Zotero connector
* Multi-language expansion


---

## 13) Testing & Quality Requirements (NON-NEGOTIABLE)

### 13.1 Test philosophy

* Every core module must have automated tests.
* Tests must be runnable locally with **one command**.
* CI must fail if:

  * any test fails
  * coverage drops below threshold
  * formatting/lint errors occur (if included)

### 13.2 Tooling (required)

* Python: `pytest`
* Coverage: `pytest-cov`
* Property/edge tests: `hypothesis` (for validators/segmenter)
* Optional but recommended:

  * `ruff` (lint)
  * `black` (format)
  * `mypy` (type checks)

### 13.3 Test command (required)

Add a `Makefile` or `justfile`:

**Makefile**

```make
test:
\tpytest -q --disable-warnings --maxfail=1 --cov=aat --cov-report=term-missing

lint:
\truff check aat tests

format:
\tblack aat tests
```

Also support:

```bash
python -m pytest
```

### 13.4 Coverage thresholds (required)

* Minimum total coverage: **85%**
* Minimum coverage for these critical files: **95%**

  * `translate/validators.py`
  * `parsing/citation.py`
  * `translate/pipeline.py`
  * `orchestrator/graph.py`

Fail CI if thresholds are not met.

### 13.5 Required test categories (must implement)

#### A) Unit tests (required)

Modules that MUST have unit tests:

* `DocxParser` (structure + text extraction)
* `Citation extraction` (multiple citation formats)
* `Segmenter` (boundary rules)
* `Validators` (citation/numeric/reference injection)
* `TermBank/PhraseBank builder` (schema + deterministic behavior)
* `Model adapter` (schema validation; mock responses)

#### B) Property tests (required)

Use `hypothesis` for:

* `NumericFidelityValidator` (random numeric patterns)
* `CitationPreservationValidator` (random combinations of citation strings)
* `Segmenter` invariants:

  * never split inside citation
  * never returns empty segment
  * concatenation of segments preserves original text (modulo whitespace normalization)

#### C) Integration tests (required)

End-to-end tests with a **mock LLM**:

* `aat translate fixtures/paper.docx --to zh --offline`

  * must produce project folder
  * must produce segments
  * must produce checkpoints
  * must produce output docx
  * must block on uncertainty unless a scripted response is provided

Key point: integration tests must NOT require real network, real OpenAlex, or paid LLM calls.

#### D) Regression tests (required)

Add a `tests/fixtures/` folder with:

* `paper_minimal.docx` (headings, citations, numbers)
* `paper_citations.docx` (varied formats)
* `paper_numbers.docx` (p-values, ranges, decimals, percents)
* `paper_references.docx` (reference section detection)

Any bug fix must add a regression test.

### 13.6 Mocking rules (required)

* All LLM calls must be mockable via dependency injection.
* Provide a `FakeLLMClient` that:

  * returns deterministic translations from fixtures
  * can insert controlled failures (citation mismatch, new number, etc.)
* All web retrieval must be mockable:

  * OpenAlex calls replaced by fixture JSON in tests
* Offline mode tests must assert:

  * no socket/network requests are made
  * if attempted, raise a clear error (`NetworkDisabledError`)

### 13.7 CI requirements (required)

Provide GitHub Actions workflow:

* run tests
* enforce coverage thresholds
* (optional) lint + format

Workflow must run on push + PR.

### 13.8 Definition of Done (testing)

A feature is “done” only if:

* unit tests added/updated
* integration test updated if workflow changes
* coverage thresholds still pass
* CI green

---

## 14) Repo additions required for testing

Add to repo root:

* `pyproject.toml` with dependencies + tool configs
* `tests/` with fixtures
* `.github/workflows/ci.yml`
* `Makefile`

---

