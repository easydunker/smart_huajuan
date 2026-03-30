#!/usr/bin/env python3
"""Translate first 5 chunks of dissertation."""

import os
from pathlib import Path

# Set up Volces API
os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
os.environ["ANTHROPIC_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/coding"

from aat.translate.llm_client import AnthropicClient, LLMError
from aat.retrieval.ingestion import LibraryIngestion

def main():
    print("=" * 70)
    print("Dissertation Translation - First 5 Chunks")
    print("=" * 70)

    # Load chunks from library
    library_dir = Path.home() / ".aat" / "library"
    ingestion = LibraryIngestion(library_dir)
    chunks = ingestion.search_by_language("en")

    if not chunks:
        print("No chunks found!")
        return

    print(f"\nFound {len(chunks)} chunks, translating first 5...\n")

    # Initialize client
    client = AnthropicClient(
        model="claude-3-5-sonnet-20241022",
        base_url="https://ark.cn-beijing.volces.com/api/coding"
    )

    # Translate first 5 chunks
    results = []
    for i, chunk in enumerate(chunks[:5], 1):
        text = chunk.get('text', '')[:500]  # Limit to 500 chars for speed

        print(f"\n{'='*70}")
        print(f"Chunk {i}/5")
        print(f"{'='*70}")
        print(f"\nSource (EN):\n{text[:200]}...")

        try:
            messages = [
                {"role": "system", "content": "You are a professional academic translator. Translate the following English academic text to Chinese (Simplified). Preserve citations and technical terms."},
                {"role": "user", "content": text}
            ]

            response = client.chat(messages, temperature=0.3)
            translation = response.get("content", "")

            print(f"\nTranslation (ZH):\n{translation[:200]}...")
            results.append({
                'chunk': i,
                'source': text,
                'translation': translation
            })

        except LLMError as e:
            print(f"\n❌ Translation failed: {e}")
            results.append({
                'chunk': i,
                'source': text,
                'translation': f"[ERROR: {e}]"
            })

    # Save results
    output_path = Path("/Users/yingyi/personal/smart_huajuan/dissertation_sample_translation.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Dissertation Sample Translation (First 5 Chunks)\n\n")
        f.write("Model: Claude 3.5 Sonnet (via Volces API)\n\n")
        f.write("---\n\n")

        for r in results:
            f.write(f"## Chunk {r['chunk']}\n\n")
            f.write("**Source (EN):**\n")
            f.write(r['source'])
            f.write("\n\n**Translation (ZH):**\n")
            f.write(r['translation'])
            f.write("\n\n---\n\n")

    print(f"\n\n{'='*70}")
    print("SAMPLE TRANSLATION COMPLETE!")
    print(f"{'='*70}")
    print(f"\nResults saved to: {output_path}")
    print(f"\nTranslated {len([r for r in results if not r['translation'].startswith('[ERROR')])}/{len(results)} chunks successfully")

if __name__ == "__main__":
    main()
