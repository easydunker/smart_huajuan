# AAT (Academic AI Translator) - Usage Examples

This document provides practical examples of using the AAT system.

## Table of Contents

1. [Library Ingestion](#library-ingestion)
2. [OpenAlex Search](#openalex-search)
3. [Retrieval Cache](#retrieval-cache)
4. [GroundingBuilder](#groundingbuilder)
5. [CLI Commands](#cli-commands)

---

## Library Ingestion

### Example 1: Ingest a Single PDF File

```python
from pathlib import Path
from aat.retrieval.ingestion import LibraryIngestion

# Initialize the ingestion system
vector_store_dir = Path.home() / ".aat" / "library"
ingestion = LibraryIngestion(vector_store_dir)

# Ingest a PDF file
pdf_path = Path("/path/to/your/paper.pdf")
result = ingestion.ingest_file(pdf_path)

print(f"Status: {result['status']}")
print(f"Chunks added: {result['chunks_added']}")
print(f"Language: {result.get('language', 'unknown')}")
```

### Example 2: Get Ingestion Statistics

```python
# Get stats about ingested files
stats = ingestion.get_stats()
print(f"Total files: {stats['total_files']}")
print(f"Total chunks: {stats['total_chunks']}")
print(f"Languages: {stats['languages']}")
```

### Example 3: Search Chunks by Language

```python
# Get all Chinese chunks
zh_chunks = ingestion.search_by_language("zh")
print(f"Found {len(zh_chunks)} Chinese chunks")

# Get all English chunks
en_chunks = ingestion.search_by_language("en")
print(f"Found {len(en_chunks)} English chunks")
```

---

## OpenAlex Search

### Example 4: Search Academic Papers

```python
from pathlib import Path
from aat.retrieval.openalex import OpenAlexClient

# Initialize with caching enabled
cache_dir = Path.home() / ".aat" / "cache"
client = OpenAlexClient(
    cache_dir=cache_dir,
    email="your@email.com",  # Recommended for polite pool
    enable_web=True  # Must be True to make network calls
)

# Search for papers
results = client.search(
    query="machine translation",
    max_results=10,
    prefer_chinese=True  # Prefer Chinese language results
)

for result in results:
    print(f"Title: {result.title}")
    print(f"Authors: {', '.join(result.authors[:3])}")
    print(f"Year: {result.publication_year}")
    print(f"DOI: {result.doi}")
    print()
```

### Example 5: Offline Mode (No Network Calls)

```python
# Create client with web disabled (offline mode)
client_offline = OpenAlexClient(
    cache_dir=cache_dir,
    enable_web=False,
)

# This will return empty results (no network calls made)
results = client_offline.search("machine translation")
print(f"Results in offline mode: {len(results)}")  # 0
```

### Example 6: Get Paper by DOI

```python
# Retrieve a specific paper by DOI
result = client.get_work_by_doi("10.1234/example")
if result:
    print(f"Found: {result.title}")
    print(f"Abstract: {result.abstract[:200]}...")
```

---

## Retrieval Cache

### Example 7: Basic Cache Operations

```python
from pathlib import Path
from aat.retrieval.cache import RetrievalCache

# Initialize cache
cache_dir = Path.home() / ".aat" / "cache"
cache = RetrievalCache(cache_dir, default_ttl_seconds=3600)  # 1 hour TTL

# Store data
cache.set("query:machine learning", {"results": [...]})

# Retrieve data (if not expired)
results = cache.get("query:machine learning")
if results:
    print("Cache hit!")
else:
    print("Cache miss or expired")

# Get cache stats
stats = cache.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Hits: {stats.hits}, Misses: {stats.misses}")
```

### Example 8: Cache with Custom TTL

```python
# Store with custom TTL (e.g., 5 minutes)
cache.set(
    "temp_data",
    {"value": 42},
    ttl_seconds=300  # 5 minutes
)
```

---

## GroundingBuilder

### Example 9: Build TermBank and PhraseBank

```python
from pathlib import Path
from aat.retrieval.grounding import GroundingBuilder

# Initialize builder
output_dir = Path.home() / ".aat" / "grounding"
builder = GroundingBuilder(output_dir)

# Process corpus chunks (from ingestion)
corpus_chunks = [
    {
        "text": "本文研究了机器学习在图像识别中的应用。实验结果表明该方法具有良好的准确性和鲁棒性。",
        "metadata": {"language": "zh", "source_path": "/path/to/paper1.pdf"}
    },
    {
        "text": "基于深度学习的模型在测试数据集上达到了95%的准确率。",
        "metadata": {"language": "zh", "source_path": "/path/to/paper2.pdf"}
    }
]

# Process corpus
result = builder.process_corpus(corpus_chunks)
print(f"Extracted {result['unique_terms']} unique terms")
print(f"Extracted {result['unique_phrases']} unique phrases")

# Save to files
paths = builder.save()
print(f"TermBank saved to: {paths['termbank']}")
print(f"PhraseBank saved to: {paths['phrasebank']}")
```

### Example 10: Load Existing TermBank and PhraseBank

```python
# Create new builder and load existing data
builder = GroundingBuilder(output_dir)
success = builder.load()

if success:
    print(f"Loaded {len(builder.termbank.entries)} terms")
    print(f"Loaded {len(builder.phrasebank.entries)} phrases")

    # Get a specific term
    term = builder.termbank.get_term("准确性")
    if term:
        print(f"Term: {term.source_term}")
        print(f"Frequency: {term.frequency}")
        print(f"Evidence: {term.evidence[:3]}")  # First 3 examples
else:
    print("No saved data found")
```

---

## CLI Commands

### Example 11: Add Library via CLI

```bash
# Add a single PDF file
./venv/bin/python -m aat add-library /path/to/paper.pdf

# Add all PDFs/DOCXs in a directory
./venv/bin/python -m aat add-library /path/to/papers/

# Add recursively (including subdirectories)
./venv/bin/python -m aat add-library /path/to/library/ -r
```

### Example 12: Resume Translation Project

```bash
# Resume a previously started translation
./venv/bin/python -m aat resume /path/to/project/
```

### Example 13: Export Chapter

```bash
# Export a specific chapter
./venv/bin/python -m aat export /path/to/project/ --chapter chapter1 -o chapter1.json

# Export full project (placeholder)
./venv/bin/python -m aat export /path/to/project/ --format docx -o translated.docx
```

---

## Complete Workflow Example

Here's a complete example showing how the components work together:

```python
#!/usr/bin/env python3
"""Complete AAT workflow example."""

from pathlib import Path
from aat.retrieval.cache import RetrievalCache
from aat.retrieval.openalex import OpenAlexClient
from aat.retrieval.ingestion import LibraryIngestion
from aat.retrieval.grounding import GroundingBuilder

# Step 1: Set up directories
base_dir = Path.home() / ".aat"
cache_dir = base_dir / "cache"
library_dir = base_dir / "library"
grounding_dir = base_dir / "grounding"

# Step 2: Search for relevant papers (cached)
cache = RetrievalCache(cache_dir)
openalex = OpenAlexClient(
    cache_dir=cache_dir,
    email="your@email.com",  # Recommended for polite pool
    enable_web=True  # Must be True to make network calls
)

results = openalex.search("machine translation chinese", max_results=5)
print(f"Found {len(results)} papers")

# Step 3: Ingest your local library
ingestion = LibraryIngestion(library_dir)

# Ingest a PDF
pdf_path = Path("/path/to/your/chinese_paper.pdf")
if pdf_path.exists():
    result = ingestion.ingest_file(pdf_path)
    print(f"Ingested {result['chunks_added']} chunks")

# Get all Chinese chunks for grounding
zh_chunks = ingestion.search_by_language("zh")
print(f"Found {len(zh_chunks)} Chinese chunks")

# Step 4: Build TermBank and PhraseBank
builder = GroundingBuilder(grounding_dir)
builder.process_corpus(zh_chunks)
builder.save()

print("Grounding resources built and saved!")

# Step 5: Use the resources for translation
# (This would integrate with the translation pipeline)
term = builder.termbank.get_term("准确性")
if term:
    print(f"Term: {term.source_term}, Freq: {term.frequency}")
```

---

## Troubleshooting

### Issue: PyPDF2 not installed
```bash
./venv/bin/pip install PyPDF2
```

### Issue: python-docx not installed
```bash
./venv/bin/pip install python-docx
```

### Issue: Cache directory permissions
```bash
mkdir -p ~/.aat/cache ~/.aat/library ~/.aat/grounding
chmod 755 ~/.aat
```

---

This completes the usage examples for the AAT system.
