#!/usr/bin/env python3
"""Simple direct translation test without pipeline."""

import os

# Check what we have
api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
base_url = os.environ.get("ANTHROPIC_BASE_URL", "")

print("=" * 70)
print("Simple Translation Test")
print("=" * 70)
print(f"\nAPI Key available: {bool(api_key)} ({api_key[:20]}... if present)")
print(f"Base URL: {base_url}")

if not api_key:
    print("\n❌ No API key available. Cannot perform translation.")
    print("\nTo test translation, you need to set one of:")
    print("  - ANTHROPIC_API_KEY (for direct Anthropic API)")
    print("  - ANTHROPIC_AUTH_TOKEN (for Volces/ByteDance proxy)")
    exit(1)

# Try different base URL formats
base_urls_to_try = [
    "https://ark.cn-beijing.volces.com/api/v3",  # Standard format
    "https://ark.cn-beijing.volces.com/api/coding/v3",  # With coding path
    base_url if base_url else None,  # From env
]

print("\n" + "=" * 70)
print("Attempting translation...")
print("=" * 70)

test_text = "This dissertation examines how mobile speakers' language use and social perception of language interact with their place-based identities."

print(f"\nSource: {test_text}")

from aat.translate.llm_client import AnthropicClient, LLMError

for url in base_urls_to_try:
    if not url:
        continue

    print(f"\nTrying base URL: {url}")

    try:
        client = AnthropicClient(
            api_key=api_key,
            base_url=url,
            model="claude-3-5-sonnet-20241022"
        )

        messages = [
            {"role": "system", "content": "You are a professional translator. Translate the following English text to Chinese (Simplified)."},
            {"role": "user", "content": test_text}
        ]

        print("Sending request...")
        response = client.chat(messages, temperature=0.3)
        translation = response.get("content", "")

        print(f"\n{'='*70}")
        print("SUCCESS!")
        print(f"{'='*70}")
        print(f"\nTranslation:\n{translation}")

        exit(0)

    except LLMError as e:
        print(f"  ❌ Failed: {e}")
        continue
    except Exception as e:
        print(f"  ❌ Error: {e}")
        continue

print(f"\n{'='*70}")
print("All attempts failed")
print(f"{'='*70}")
print("\nTroubleshooting:")
print("1. Check that ANTHROPIC_AUTH_TOKEN is set correctly")
print("2. Verify the base URL format with your API provider")
print("3. Ensure you have network connectivity to the API endpoint")
