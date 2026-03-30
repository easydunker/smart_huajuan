# AAT - Academic AI Translator

Local-first CLI tool for translating academic documents from English to Chinese.

## Features

- Reference-aware translation with grounding from free academic sources
- Deterministic anti-hallucination checks
- User-in-the-loop comments and clarification
- Offline mode support
- Local model support (Ollama)

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Translate a document
aat translate paper.docx --to zh

# Add files to local library
aat add-library paper.pdf

# Resume a project
aat resume project-folder

# Export results
aat export project-folder --format docx
```

## Development

```bash
# Run tests
make test

# Lint code
make lint

# Format code
make format
```

## Milestone Progress

- M1: CLI + DOCX parse + segmentation - COMPLETE
- M2: Translation draft + validators + checkpoints - PENDING
- M3: Localhost UI + comment loop - PENDING
- M4: Library ingest + embeddings + vector DB - PENDING
- M5: OpenAlex retrieval + phrasebank/termbank - PENDING
- M6: Global pass + docx export polish - PENDING
