#!/usr/bin/env python3
"""Process Yuhan Lin's dissertation with AAT."""

from pathlib import Path
from aat.retrieval.ingestion import LibraryIngestion
from aat.retrieval.grounding import GroundingBuilder


def main():
    print("=" * 70)
    print("Processing Dissertation: Yuhan Lin (2018)")
    print("=" * 70)

    # Setup
    library_dir = Path.home() / ".aat" / "library"
    grounding_dir = Path.home() / ".aat" / "grounding"

    # Step 1: Access ingested dissertation
    print("\n📚 Step 1: Accessing ingested dissertation...")
    ingestion = LibraryIngestion(library_dir)
    stats = ingestion.get_stats()
    print(f"   Total files: {stats['total_files']}")
    print(f"   Total chunks: {stats['total_chunks']}")

    # Step 2: Get English chunks
    print("\n📖 Step 2: Retrieving English chunks...")
    en_chunks = ingestion.search_by_language("en")
    print(f"   Found {len(en_chunks)} English chunks")

    # Step 3: Build grounding resources
    print("\n🔨 Step 3: Building TermBank and PhraseBank...")
    builder = GroundingBuilder(grounding_dir)

    # Process first 50 chunks for demo
    demo_chunks = en_chunks[:50]
    result = builder.process_corpus(demo_chunks)

    print(f"   ✓ Unique terms: {result['unique_terms']}")
    print(f"   ✓ Unique phrases: {result['unique_phrases']}")

    # Save
    paths = builder.save()
    print(f"\n💾 Resources saved:")
    print(f"   {paths['termbank']}")
    print(f"   {paths['phrasebank']}")

    print("\n" + "=" * 70)
    print("Processing Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
