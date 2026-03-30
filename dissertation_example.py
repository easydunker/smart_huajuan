#!/usr/bin/env python3
"""
Dissertation Translation Workflow Example

This script demonstrates a complete workflow for processing
Yuhan Lin's 2018 dissertation using AAT.
"""

from pathlib import Path
from aat.retrieval.ingestion import LibraryIngestion
from aat.retrieval.grounding import GroundingBuilder

def main():
    print("=" * 70)
    print("AAT Dissertation Processing Workflow")
    print("=" * 70)
    print()

    # Configuration
    dissertation_path = Path("/Users/yingyi/Downloads/Dissertation_YuhanLin2018.pdf")
    base_dir = Path.home() / ".aat"
    library_dir = base_dir / "library"
    grounding_dir = base_dir / "grounding"

    print(f"📄 Dissertation: {dissertation_path.name}")
    print(f"📊 File size: {dissertation_path.stat().st_size / (1024*1024):.1f} MB")
    print()

    # Step 1: Initialize Library Ingestion
    print("Step 1: Initializing Library Ingestion...")
    ingestion = LibraryIngestion(library_dir)
    print(f"  ✓ Library directory: {library_dir}")
    print()

    # Step 2: Ingest the dissertation
    print("Step 2: Ingesting dissertation (this may take a moment)...")
    try:
        result = ingestion.ingest_file(dissertation_path)
        print(f"  ✓ Status: {result['status']}")
        print(f"  ✓ Chunks created: {result['chunks_added']}")
        print(f"  ✓ Detected language: {result.get('language', 'unknown')}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return
    print()

    # Step 3: Get library statistics
    print("Step 3: Library Statistics...")
    stats = ingestion.get_stats()
    print(f"  📊 Total files: {stats['total_files']}")
    print(f"  📄 Total chunks: {stats['total_chunks']}")
    print(f"  🌐 Languages: {stats['languages']}")
    print()

    # Step 4: Get English chunks
    print("Step 4: Retrieving English chunks...")
    en_chunks = ingestion.search_by_language("en")
    print(f"  📚 Found {len(en_chunks)} English chunks")
    print()

    # Step 5: Initialize GroundingBuilder
    print("Step 5: Initializing GroundingBuilder...")
    builder = GroundingBuilder(grounding_dir)
    print(f"  ✓ Grounding directory: {grounding_dir}")
    print()

    # Step 6: Build TermBank and PhraseBank (limit to first 100 chunks for demo)
    print("Step 6: Building TermBank and PhraseBank...")
    print(f"  ⏳ Processing first 100 chunks (demo limit)...")

    # Process limited chunks for demo
    demo_chunks = en_chunks[:100]
    result = builder.process_corpus(demo_chunks)

    print(f"  ✓ Unique terms: {result['unique_terms']}")
    print(f"  ✓ Unique phrases: {result['unique_phrases']}")
    print(f"  ✓ Total term occurrences: {result['terms']}")
    print(f"  ✓ Total phrase occurrences: {result['phrases']}")
    print()

    # Step 7: Save resources
    print("Step 7: Saving resources...")
    paths = builder.save()
    print(f"  💾 TermBank: {paths['termbank']}")
    print(f"  💾 PhraseBank: {paths['phrasebank']}")
    print()

    # Step 8: Show sample terms
    if builder.termbank.entries:
        print("Step 8: Sample Extracted Terms...")
        for i, (term_id, term) in enumerate(list(builder.termbank.entries.items())[:5]):
            print(f"  • {term.source_term} (freq: {term.frequency})")
        print()

    # Summary
    print("=" * 70)
    print("WORKFLOW COMPLETE!")
    print("=" * 70)
    print()
    print(f"📄 Dissertation: {dissertation_path.name}")
    print(f"📚 Total chunks: {len(en_chunks)}")
    print(f"📊 Terms extracted: {result['unique_terms']}")
    print(f"📊 Phrases extracted: {result['unique_phrases']}")
    print()
    print("Next steps for translation:")
    print("  1. Use ./venv/bin/python -m aat resume <project>")
    print("  2. Or integrate with translation pipeline")
    print()

if __name__ == "__main__":
    main()
