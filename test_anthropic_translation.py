#!/usr/bin/env python3
"""Test Anthropic translation with a simple example."""

import os
from aat.translate.llm_client import AnthropicClient, LLMError

def main():
    print("=" * 70)
    print("Testing Anthropic Claude Translation")
    print("=" * 70)

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ ANTHROPIC_API_KEY not set!")
        print("Please set the ANTHROPIC_API_KEY environment variable.")
        return

    print(f"\n✓ API key found: {api_key[:10]}...")

    # Initialize client
    try:
        client = AnthropicClient(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022"
        )
        print(f"✓ Client initialized with model: {client.model}")
    except LLMError as e:
        print(f"❌ Failed to initialize client: {e}")
        return

    # Test simple translation
    print("\n" + "-" * 70)
    print("Test 1: Simple Translation")
    print("-" * 70)

    messages = [
        {"role": "system", "content": "You are a professional translator. Translate the following English text to Chinese (Simplified)."},
        {"role": "user", "content": "Hello, how are you today?"}
    ]

    try:
        response = client.chat(messages, temperature=0.3)
        translation = response.get("content", "")
        print(f"\nInput:    'Hello, how are you today?'")
        print(f"Output:   '{translation}'")
        print("\n✓ Simple translation successful!")
    except LLMError as e:
        print(f"❌ Translation failed: {e}")
        return

    # Test structured output with JSON schema
    print("\n" + "-" * 70)
    print("Test 2: Structured Output with JSON Schema")
    print("-" * 70)

    messages = [
        {"role": "system", "content": "You are a professional translator. Translate the academic text to Chinese (Simplified)."},
        {"role": "user", "content": "This dissertation examines how mobile speakers' language use and social perception of language interact with their place-based identities."}
    ]

    json_schema = {
        "type": "object",
        "properties": {
            "translation": {
                "type": "string",
                "description": "The translated text in Chinese (Simplified)"
            },
            "uncertainties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "span": {"type": "string"},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        },
        "required": ["translation"]
    }

    try:
        response = client.chat(messages, json_schema=json_schema, temperature=0.3)
        content = response.get("content", {})

        if isinstance(content, dict):
            translation = content.get("translation", "")
            uncertainties = content.get("uncertainties", [])

            print(f"\nInput:    'This dissertation examines how mobile speakers...'")
            print(f"Output:   '{translation[:100]}...'" if len(translation) > 100 else f"Output:   '{translation}'")
            print(f"Uncertainties: {len(uncertainties)}")
            print("\n✓ Structured output translation successful!")
        else:
            print(f"\n✓ Translation: '{content}'")
    except LLMError as e:
        print(f"❌ Structured translation failed: {e}")
        return

    print("\n" + "=" * 70)
    print("All tests passed! Anthropic Claude integration is working.")
    print("=" * 70)


if __name__ == "__main__":
    main()
