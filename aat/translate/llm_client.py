"""LLM client abstraction supporting multiple providers."""

import os
from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Send chat completion request to LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            json_schema: Optional JSON schema for structured output.
            **kwargs: Additional provider-specific arguments.

        Returns:
            Response dict with parsed content.

        Raises:
            LLMError: If request fails.
        """
        pass


class LLMError(Exception):
    """Exception raised for LLM client errors."""


class AnthropicClient(LLMClient):
    """Anthropic Claude client for API inference."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        base_url: str | None = None,
        auth_token: str | None = None
    ) -> None:
        """
        Initialize Anthropic client.

        Args:
            model: Model name to use (e.g., claude-3-5-sonnet-20241022).
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            base_url: Custom base URL for API proxy (e.g., Volces).
            auth_token: Alternative auth token for custom API endpoints.
        """
        self.model = model

        # Get from parameters or environment
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or None
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL") or None
        self.auth_token = auth_token or os.environ.get("ANTHROPIC_AUTH_TOKEN") or None

        # If no API key but auth_token available, use auth_token as api_key
        if not self.api_key and self.auth_token:
            self.api_key = self.auth_token

        self._client: Any = None

        try:
            import anthropic

            client_kwargs = {}

            if self.api_key:
                client_kwargs["api_key"] = self.api_key

            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            self._client = anthropic.Anthropic(**client_kwargs)

        except ImportError as e:
            raise LLMError(f"Failed to import anthropic: {e}. Install with: pip install anthropic")
        except Exception as e:
            if "api_key" in str(e).lower() or "auth" in str(e).lower():
                raise LLMError(
                    "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable, "
                    "ANTHROPIC_AUTH_TOKEN, or pass api_key parameter."
                )
            raise LLMError(f"Failed to initialize Anthropic client: {e}")

    def chat(
        self,
        messages: list[dict],
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Send chat completion request to Anthropic.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            json_schema: Optional JSON schema for structured output.
            **kwargs: Additional arguments (temperature, max_tokens, etc).

        Returns:
            Response dict with 'content' key.
        """
        try:
            import json

            # Convert messages to Anthropic format (system message separate)
            system_message = None
            chat_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                elif msg["role"] == "user":
                    chat_messages.append({"role": "user", "content": msg["content"]})
                elif msg["role"] == "assistant":
                    chat_messages.append({"role": "assistant", "content": msg["content"]})

            # Build request parameters
            request_params = {
                "model": self.model,
                "messages": chat_messages,
                "max_tokens": kwargs.get("max_tokens", 4096),
            }

            if system_message:
                request_params["system"] = system_message

            if "temperature" in kwargs:
                request_params["temperature"] = kwargs["temperature"]

            # Handle JSON schema for structured output
            if json_schema is not None:
                # Use tool calling for structured output
                tool_name = "translate_segment"
                request_params["tools"] = [{
                    "name": tool_name,
                    "description": "Translate the academic text segment",
                    "input_schema": json_schema
                }]
                request_params["tool_choice"] = {"type": "tool", "name": tool_name}

            # Make the API call
            response = self._client.messages.create(**request_params)

            # Parse response
            if json_schema is not None and response.content:
                # Extract tool use result
                for content in response.content:
                    if content.type == "tool_use":
                        return {"content": content.input}
                # Fallback to text content
                return {"content": response.content[0].text if response.content else ""}
            else:
                return {"content": response.content[0].text if response.content else ""}

        except Exception as e:
            raise LLMError(f"Anthropic request failed: {e}")


class OllamaClient(LLMClient):
    """Ollama client for free local model inference."""

    def __init__(self, model: str = "qwen2.5:14b", host: str = "http://localhost:11434") -> None:
        """
        Initialize Ollama client.

        Args:
            model: Model name to use.
            host: Ollama API host URL.
        """
        self.model = model
        self.host = host
        self._client: Any = None

        try:
            import ollama

            self._client = ollama.Client(host=host)
        except ImportError as e:
            raise LLMError(f"Failed to import ollama: {e}. Install with: pip install ollama")

    def chat(
        self,
        messages: list[dict],
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Send chat completion request to Ollama.

        Args:
            messages: List of message dicts.
            json_schema: Optional JSON schema for structured output.
            **kwargs: Additional arguments (temperature, etc).

        Returns:
            Response dict with 'content' key.
        """
        try:
            response = self._client.chat(
                model=self.model,
                messages=messages,
                format="json" if json_schema else None,
                options=kwargs.get("options", {}),
                stream=kwargs.get("stream", False),
            )

            # Parse response
            if json_schema:
                return {"content": response.message.content}
            else:
                return {"content": response.message.content}

        except Exception as e:
            raise LLMError(f"Ollama request failed: {e}")


class OpenAIClient(LLMClient):
    """OpenAI client for paid API inference."""

    def __init__(self, model: str = "gpt-4", api_key: str | None = None) -> None:
        """
        Initialize OpenAI client.

        Args:
            model: Model name to use.
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
        """
        self.model = model
        self.api_key = api_key
        self._client: Any = None

        try:
            import openai

            self._client = openai.OpenAI(api_key=api_key)
        except ImportError as e:
            raise LLMError(f"Failed to import openai: {e}. Install with: pip install openai")

    def chat(
        self,
        messages: list[dict],
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Send chat completion request to OpenAI.

        Args:
            messages: List of message dicts.
            json_schema: Optional JSON schema for structured output.
            **kwargs: Additional arguments (temperature, etc).

        Returns:
            Response dict with 'content' key.
        """
        try:
            import json

            # Convert messages to OpenAI format
            openai_messages = [
                {"role": msg["role"], "content": msg["content"]} for msg in messages
            ]

            if json_schema:
                # Use structured output
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                    **kwargs,
                )

                # Parse JSON response
                return {"content": json.loads(response.choices[0].message.content)}
            else:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=openai_messages,
                    **kwargs,
                )

                return {"content": response.choices[0].message.content}

        except Exception as e:
            raise LLMError(f"OpenAI request failed: {e}")


class FakeLLMClient(LLMClient):
    """Fake LLM client for testing with deterministic responses."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        """
        Initialize fake LLM client.

        Args:
            responses: Dict mapping prompts to deterministic responses.
                     If None, returns default mock responses.
        """
        self.responses = responses or {}
        self.call_count = 0
        self.response_queue: list[dict] = []

    def chat(
        self,
        messages: list[dict],
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Return deterministic response based on last user message.

        Args:
            messages: List of message dicts.
            json_schema: Optional JSON schema for schema-aware responses.
            **kwargs: Additional arguments (ignored in fake).

        Returns:
            Mock response dict.
        """
        self.call_count += 1

        if self.response_queue:
            return self.response_queue.pop(0)

        last_user_msg = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break

        if last_user_msg and last_user_msg in self.responses:
            return self.responses[last_user_msg]

        if json_schema is not None:
            props = json_schema.get("properties", {})
            if "issues" in props:
                return {"content": {"issues": []}}
            if "segment_type" in props:
                return {
                    "content": {
                        "segment_type": "其他",
                        "key_terms": [],
                        "special_formats": [],
                        "translation_strategy": "",
                    }
                }
            return {
                "content": {
                    "translation": "这是翻译文本。",
                    "uncertainties": [],
                    "notes": ["Used standard translation for test text."],
                }
            }
        else:
            return {"content": "这是翻译文本。"}

    def set_response(self, prompt: str, response: dict | str) -> None:
        """
        Set a specific response for a prompt.

        Args:
            prompt: The prompt text to match.
            response: Response dict or string content.
        """
        if isinstance(response, str):
            response = {"content": response}
        self.responses[prompt] = response

    def reset(self) -> None:
        """Reset call count and responses."""
        self.call_count = 0
        self.responses = {}


def create_client(provider: str, **kwargs: Any) -> LLMClient:
    """
    Factory function to create LLM client.

    Args:
        provider: Provider name ('ollama', 'openai', 'anthropic', or 'fake').
        **kwargs: Provider-specific arguments.

    Returns:
        LLMClient instance.

    Raises:
        ValueError: If provider is unknown.
    """
    provider = provider.lower()

    # Valid kwargs for each provider to avoid passing unexpected args
    ollama_params = {"model", "host"}
    openai_params = {"model", "api_key"}
    anthropic_params = {"model", "api_key", "base_url", "auth_token"}
    fake_params = {"responses"}

    if provider == "ollama":
        # Only include non-None kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None and k in ollama_params}
        return OllamaClient(**filtered_kwargs)
    elif provider == "openai":
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None and k in openai_params}
        return OpenAIClient(**filtered_kwargs)
    elif provider == "anthropic":
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None and k in anthropic_params}
        return AnthropicClient(**filtered_kwargs)
    elif provider == "fake":
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None and k in fake_params}
        return FakeLLMClient(**filtered_kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use 'ollama', 'openai', 'anthropic', or 'fake'")
