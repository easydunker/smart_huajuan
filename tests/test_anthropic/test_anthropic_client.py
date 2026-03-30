"""Tests for Anthropic Claude provider."""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock

from aat.translate.llm_client import AnthropicClient, LLMError, create_client


class TestAnthropicClient:
    """Test Anthropic Claude client."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client

            # Clear env vars for this test
            with patch.dict(os.environ, {}, clear=True):
                client = AnthropicClient(api_key="test-key", model="claude-3-5-sonnet-20241022")

            assert client.api_key == "test-key"
            assert client.model == "claude-3-5-sonnet-20241022"
            mock_anthropic.assert_called_once_with(api_key="test-key")

    def test_init_without_api_key_uses_env(self):
        """Test initialization without API key uses environment variable."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client

            # Clear env vars for this test
            with patch.dict(os.environ, {}, clear=True):
                client = AnthropicClient(model="claude-3-5-sonnet-20241022")

            # When env vars are empty, api_key should be None
            assert client.api_key is None
            mock_anthropic.assert_called_once_with()  # No api_key arg means use env

    def test_init_import_error(self):
        """Test import error handling."""
        with patch("builtins.__import__", side_effect=ImportError("No module named anthropic")):
            with pytest.raises(LLMError) as exc_info:
                AnthropicClient(api_key="test-key")
            assert "Failed to import anthropic" in str(exc_info.value)

    def test_init_missing_api_key_error(self):
        """Test clear error message when API key is missing."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.side_effect = Exception("Missing api_key")

            with pytest.raises(LLMError) as exc_info:
                AnthropicClient()
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)
            assert "environment variable" in str(exc_info.value)

    def test_chat_simple_message(self):
        """Test simple chat message."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text="This is the translation.")]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            client = AnthropicClient(api_key="test-key")
            messages = [{"role": "user", "content": "Translate this text."}]
            result = client.chat(messages)

            assert result["content"] == "This is the translation."
            mock_client.messages.create.assert_called_once()

    def test_chat_with_system_message(self):
        """Test chat with system message."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text="Translated text.")]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            client = AnthropicClient(api_key="test-key")
            messages = [
                {"role": "system", "content": "You are a translator."},
                {"role": "user", "content": "Hello"}
            ]
            result = client.chat(messages)

            assert result["content"] == "Translated text."
            # Check that system message was passed separately
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs.get("system") == "You are a translator."

    def test_chat_with_json_schema(self):
        """Test chat with JSON schema for structured output."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_message = Mock()
            # Simulate tool_use response
            tool_result = {"translation": "这是翻译。", "uncertainties": []}
            mock_content = Mock()
            mock_content.type = "tool_use"
            mock_content.input = tool_result
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            client = AnthropicClient(api_key="test-key")
            messages = [{"role": "user", "content": "Translate this."}]
            json_schema = {
                "type": "object",
                "properties": {
                    "translation": {"type": "string"},
                    "uncertainties": {"type": "array"}
                }
            }
            result = client.chat(messages, json_schema=json_schema)

            assert result["content"] == tool_result

    def test_chat_error_handling(self):
        """Test error handling in chat."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create.side_effect = Exception("API Error")
            mock_anthropic.return_value = mock_client

            client = AnthropicClient(api_key="test-key")
            messages = [{"role": "user", "content": "Hello"}]

            with pytest.raises(LLMError) as exc_info:
                client.chat(messages)
            assert "Anthropic request failed" in str(exc_info.value)


class TestCreateClientAnthropic:
    """Test create_client factory with Anthropic."""

    def test_create_anthropic_client(self):
        """Test factory creates AnthropicClient."""
        with patch("aat.translate.llm_client.AnthropicClient") as mock_client_class:
            mock_instance = Mock(spec=AnthropicClient)
            mock_client_class.return_value = mock_instance

            result = create_client("anthropic", model="claude-3-5-sonnet", api_key="test-key")

            mock_client_class.assert_called_once_with(model="claude-3-5-sonnet", api_key="test-key")

    def test_create_anthropic_client_lowercase(self):
        """Test factory is case-insensitive."""
        with patch("aat.translate.llm_client.AnthropicClient") as mock_client_class:
            mock_instance = Mock(spec=AnthropicClient)
            mock_client_class.return_value = mock_instance

            # Clear env vars for this test
            with patch.dict(os.environ, {}, clear=True):
                result = create_client("ANTHROPIC", model="claude-3-opus")

            mock_client_class.assert_called_once_with(model="claude-3-opus")
