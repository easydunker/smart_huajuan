#!/usr/bin/env python3
"""Test translation on a single small chunk with detailed error output."""

import os

# Set up environment
os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
os.environ["ANTHROPIC_BASE_URL"] = "https://ark.cn-beijing.volces.com/api/v3"

from aat.translate.llm_client import AnthropicClient, LLMError

def main():
    print("=" * 70)
    print("Single Chunk Translation Test")
    print("=" * 70)

    # Small test text
    test_text = "This dissertation examines how mobile speakers' language use and social perception of language interact with their place-based identities."

    print(f"\nSource text:\n{test_text}\n")

    try:
        # Initialize client
        client = AnthropicClient(
            model="claude-3-5-sonnet-20241022",
            base_url="https://ark.cn-beijing.volces.com/api/v3"
        )
        print(f"✓ Client initialized")
        print(f"  Model: {client.model}")
        print(f"  Base URL: {client.base_url}")

        # Prepare translation prompt
        messages = [
            {"role": "system", "content": "You are a professional academic translator. Translate the following English text to Chinese (Simplified). Provide only the translation, no explanations."},
            {"role": "user", "content": test_text}
        ]

        print("\nSending translation request...")
        response = client.chat(messages, temperature=0.3)

        translation = response.get("content", "")
        print(f"\n{'='*70}")
        print("TRANSLATION RESULT")
        print(f"{'='*70}")
        print(f"\n{translation}")
        print(f"\n{'='*70}")
        print("✅ Translation successful!")

    except LLMError as e:
        print(f"\n❌ LLM Error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
