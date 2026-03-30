#!/usr/bin/env python3
"""Quick translation test - first 5 chunks only."""

import os
from pathlib import Path

# Set up environment for Volces API
os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
os.environ["ANTHROPIC_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/v3"

from aat.storage.models import DocumentModel, TranslationProject, Paragraph, Section
from aat.translate.pipeline import TranslationPipeline, PipelineConfig
from aat.retrieval.ingestion import LibraryIngestion

def main():
    print("=" * 70)
    print("Quick Translation Test - First 5 Chunks")
    print("=" * 70)

    # Load chunks from library
    library_dir = Path.home() / ".aat" / "library"
    ingestion = LibraryIngestion(library_dir)
    chunks = ingestion.search_by_language("en")

    if not chunks:
        print("No chunks found in library!")
        return

    # Take only first 5 chunks
    test_chunks = chunks[:5]
    print(f"\nLoaded {len(chunks)} total chunks, translating first {len(test_chunks)}...")

    # Create paragraphs
    paragraphs = []
    for i, chunk in enumerate(test_chunks):
        para = Paragraph(
            pid=f"para_{i}",
            text=chunk.get('text', '')
        )
        paragraphs.append(para)
        print(f"\nChunk {i+1}:")
        print(f"  Text: {chunk.get('text', '')[:150]}...")

    # Create document structure
    section = Section(
        heading="Chapter 1",
        paragraphs=paragraphs
    )

    doc_model = DocumentModel(
        doc_id="quick_test",
        title="Quick Translation Test",
        sections=[section],
        references=[],
        citations=[]
    )

    project = TranslationProject(
        project_id="quick_test_proj",
        document=doc_model
    )

    # Configure with Anthropic
    print("\n" + "-" * 70)
    print("Configuring Anthropic Claude...")
    print(f"  Model: claude-3-5-sonnet-20241022")
    print(f"  Base URL: {os.environ.get('ANTHROPIC_BASE_URL', 'default')}")
    print("-" * 70)

    config = PipelineConfig(
        llm_provider="anthropic",
        llm_model="claude-3-5-sonnet-20241022",
        enable_checkpoints=True
    )

    # Run translation
    print("\nStarting translation pipeline...")
    try:
        pipeline = TranslationPipeline(project, config=config)
        completed_project = pipeline.run()

        # Show results
        print("\n" + "=" * 70)
        print("TRANSLATION COMPLETE!")
        print("=" * 70)

        # Access translation segments
        segments = getattr(completed_project, 'translation_segments', [])
        if not segments:
            segments = getattr(completed_project, 'segments', [])

        for i, seg in enumerate(segments[:5], 1):
            print(f"\n--- Segment {i} ---")
            if hasattr(seg, 'source_text'):
                print(f"Source: {seg.source_text[:200]}...")
            if hasattr(seg, 'translation') and seg.translation:
                print(f"Translation: {seg.translation[:200]}...")
            else:
                print("Translation: (pending)")

    except Exception as e:
        print(f"\n❌ Translation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
