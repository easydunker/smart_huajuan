#!/usr/bin/env python3
"""Test translation with only 10 chunks to verify logging."""

import os
import sys
from pathlib import Path

# Set up environment
os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
os.environ["ANTHROPIC_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/coding"

from aat.storage.models import DocumentModel, TranslationProject, Paragraph, Section
from aat.translate.pipeline import TranslationPipeline, PipelineConfig
from aat.retrieval.ingestion import LibraryIngestion

def main():
    print("=" * 70)
    print("TEST TRANSLATION - 10 CHUNKS ONLY")
    print("=" * 70)

    # Load chunks
    library_dir = Path.home() / ".aat" / "library"
    ingestion = LibraryIngestion(library_dir)
    chunks = ingestion.search_by_language("en")

    if not chunks:
        print("No chunks found!")
        return

    # Take only 10 chunks
    test_chunks = chunks[:10]
    print(f"\nTotal chunks: {len(chunks)}")
    print(f"Testing with: {len(test_chunks)} chunks\n")

    # Create paragraphs
    paragraphs = []
    for i, chunk in enumerate(test_chunks):
        para = Paragraph(
            pid=f"para_{i}",
            text=chunk.get('text', '')
        )
        paragraphs.append(para)

    # Create document
    section = Section(heading="Test Section", paragraphs=paragraphs)
    doc_model = DocumentModel(
        doc_id="test_10_chunks",
        title="Test 10 Chunks",
        sections=[section],
        references=[],
        citations=[]
    )

    project = TranslationProject(
        project_id="test_proj",
        document=doc_model
    )

    # Configure
    config = PipelineConfig(
        llm_provider="anthropic",
        llm_model="claude-3-5-sonnet-20241022",
        enable_checkpoints=True
    )

    print("Starting pipeline...\n")

    # Run
    try:
        pipeline = TranslationPipeline(project, config=config)
        completed = pipeline.run()

        print("\n" + "=" * 70)
        print("TRANSLATION COMPLETE!")
        print("=" * 70)

        # Export to file
        output_path = "/Users/yingyi/personal/smart_huajuan/test_10_chunks_output.md"
        print(f"\nExporting to {output_path}...")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Test Translation - 10 Chunks\n\n")

            # Get segments from project
            segments = getattr(completed, 'segments', [])
            print(f"Found {len(segments)} segments")

            for i, seg in enumerate(segments, 1):
                f.write(f"## Segment {i}\n\n")

                # Get source and translation
                source_text = ""
                translation = ""

                if hasattr(seg, 'segment') and seg.segment:
                    source_text = getattr(seg.segment, 'source_text', '')
                if hasattr(seg, 'translation'):
                    translation = seg.translation or ""

                # Write to file
                f.write("**Source (EN):**\n")
                f.write(source_text[:500] if source_text else "N/A")
                f.write("\n\n")

                f.write("**Translation (ZH):**\n")
                f.write(translation[:500] if translation else "*[No translation]*")
                f.write("\n\n---\n\n")

                # Also print to console
                print(f"\n--- Segment {i} ---")
                print(f"Source: {source_text[:100]}...")
                print(f"Translation: {translation[:100] if translation else 'N/A'}...")

        print(f"\n✅ Exported to {output_path}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
