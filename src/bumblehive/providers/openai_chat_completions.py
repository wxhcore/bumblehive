import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from inspect import isawaitable
from typing import Any

from ..agent.types import AgentError
from ..tools.calls import ToolCall, parse_tool_call
from .base import GenerationConfig, ModelProvider, ModelRequest, ModelResponse


_ALLOWED_MESSAGE_KEYS = frozenset(
    {
        "role",
        "content",
        "tool_calls",
        "tool_call_id",
        "name",
    }
)


class OpenAIChatCompletionsProvider(ModelProvider):
    """Provider for OpenAI-compatible Chat Completions APIs."""

    def __init__(
        self,
        *,
        model: str = "gpt-5.4",
        api_key: str | None = None,
        base_url: str | None = None,
        default_generation: GenerationConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.default_generation = default_generation or GenerationConfig()
        self._client = client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            response = await self._client_or_create().chat.completions.create(
                **self._build_payload(request)
            )
        except Exception as exc:
            return self._error_response_from_exception(exc)

        try:
            return self._parse_response(response)
        except Exception as exc:
            return ModelResponse(
                content=f"Error parsing model response: {exc}",
                finish_reason="error",
                error=AgentError(
                    code="model_response_parse_error",
                    message=str(exc),
                ),
            )

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is required for OpenAIChatCompletionsProvider. "
                "Install it with: pip install openai"
            ) from exc

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        return self._client

    async def close(self) -> None:
        """Close the cached OpenAI SDK client, if it was created."""
        client = self._client
        self._client = None
        if client is None:
            return

        await self._close_client(client)

    @staticmethod
    async def _close_client(client: Any) -> None:
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
        else:
            aclose = getattr(client, "aclose", None)
            if not callable(aclose):
                return
            result = aclose()

        if isawaitable(result):
            await result

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        generation = request.generation or self.default_generation
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": self._sanitize_messages(request.messages),
        }

        self._apply_generation(payload, generation)

        if request.tools:
            payload["tools"] = list(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"
        elif request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        return payload

    @staticmethod
    def _apply_generation(
        payload: dict[str, Any],
        generation: GenerationConfig,
    ) -> None:
        payload["max_completion_tokens"] = max(1, generation.max_tokens)
        if generation.temperature is not None:
            payload["temperature"] = generation.temperature
        if generation.reasoning_effort is not None:
            payload["reasoning_effort"] = generation.reasoning_effort

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        for message in messages:
            clean = {
                key: value
                for key, value in message.items()
                if key in _ALLOWED_MESSAGE_KEYS
            }

            if clean.get("role") == "assistant" and clean.get("tool_calls"):
                clean["content"] = clean.get("content") or None
            elif clean.get("content") in ("", None):
                clean["content"] = "(empty)"

            sanitized.append(clean)
        return sanitized

    def _parse_response(self, response: Any) -> ModelResponse:
        choice = self._first_choice(response)
        message = self._get(choice, "message")
        if message is None:
            raise ValueError("response choice is missing message")

        return ModelResponse(
            content=self._get(message, "content"),
            tool_calls=self._parse_tool_calls(self._get(message, "tool_calls")),
            finish_reason=self._get(choice, "finish_reason") or "stop",
            usage=self._parse_usage(self._get(response, "usage")),
            refusal=self._get(message, "refusal"),
            reasoning_content=self._parse_reasoning_content(message),
        )

    @staticmethod
    def _first_choice(response: Any) -> Any:
        choices = OpenAIChatCompletionsProvider._get(response, "choices")
        if not choices:
            raise ValueError("response is missing choices")
        return choices[0]

    def _parse_tool_calls(self, raw_tool_calls: Any) -> list[ToolCall]:
        return [
            self._parse_tool_call(raw_call)
            for raw_call in (raw_tool_calls or [])
        ]

    def _parse_tool_call(self, raw_call: Any) -> ToolCall:
        function = self._get(raw_call, "function")
        if function is None:
            raise ValueError("tool call is missing function payload")

        return parse_tool_call(
            {
                "id": self._get(raw_call, "id"),
                "function": {
                    "name": self._get(function, "name"),
                    "arguments": self._get(function, "arguments") or "{}",
                },
            }
        )

    @staticmethod
    def _parse_reasoning_content(message: Any) -> str | None:
        reasoning = (
            OpenAIChatCompletionsProvider._get(message, "reasoning_content")
            or OpenAIChatCompletionsProvider._get(message, "reasoning")
        )
        return reasoning if isinstance(reasoning, str) else None

    @staticmethod
    def _parse_usage(usage: Any) -> dict[str, int]:
        if usage is None:
            return {}

        result: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = OpenAIChatCompletionsProvider._safe_int(
                OpenAIChatCompletionsProvider._get(usage, key)
            )
            if value is not None:
                result[key] = value

        cached_tokens = OpenAIChatCompletionsProvider._safe_int(
            OpenAIChatCompletionsProvider._get(
                OpenAIChatCompletionsProvider._get(usage, "prompt_tokens_details"),
                "cached_tokens",
            )
        )
        if cached_tokens:
            result["cached_tokens"] = cached_tokens

        return result

    @classmethod
    def _error_response_from_exception(cls, exc: Exception) -> ModelResponse:
        metadata = cls._extract_error_metadata(exc)
        message = cls._format_error_message(exc)
        error = AgentError(
            code=cls._classify_error_code(
                status_code=metadata["error_status_code"],
                error_kind=metadata["error_kind"],
                error_type=metadata["error_type"],
                error_code=metadata["error_code"],
                message=message,
            ),
            message=message,
            recoverable=cls._is_recoverable_error(
                status_code=metadata["error_status_code"],
                error_kind=metadata["error_kind"],
                error_type=metadata["error_type"],
                error_code=metadata["error_code"],
                message=message,
            ),
        )

        return ModelResponse(
            content=f"Error calling model: {message}",
            finish_reason="error",
            error=error,
            retry_after=metadata["retry_after"],
            error_status_code=metadata["error_status_code"],
            error_kind=metadata["error_kind"],
            error_type=metadata["error_type"],
            error_code=metadata["error_code"],
        )

    @classmethod
    def _extract_error_metadata(cls, exc: Exception) -> dict[str, Any]:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        payload = (
            getattr(exc, "body", None)
            or getattr(exc, "doc", None)
            or getattr(response, "text", None)
        )
        if payload is None and response is not None:
            response_json = getattr(response, "json", None)
            if callable(response_json):
                try:
                    payload = response_json()
                except Exception:
                    payload = None

        status_code = getattr(exc, "status_code", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)

        error_kind = cls._error_kind_from_exception(exc)
        error_type, error_code = cls._extract_error_type_code(payload)

        return {
            "error_status_code": cls._safe_int(status_code),
            "error_kind": error_kind,
            "error_type": error_type,
            "error_code": error_code,
            "retry_after": cls._extract_retry_after_from_headers(headers),
        }

    @staticmethod
    def _format_error_message(exc: Exception) -> str:
        body = (
            getattr(exc, "doc", None)
            or getattr(exc, "body", None)
            or getattr(getattr(exc, "response", None), "text", None)
        )
        if body is not None:
            text = body if isinstance(body, str) else str(body)
            if text.strip():
                return text.strip()[:500]
        return str(exc)

    @staticmethod
    def _error_kind_from_exception(exc: Exception) -> str | None:
        name = exc.__class__.__name__.lower()
        if "timeout" in name:
            return "timeout"
        if "connection" in name:
            return "connection"
        return None

    @classmethod
    def _classify_error_code(
        cls,
        *,
        status_code: int | None,
        error_kind: str | None,
        error_type: str | None,
        error_code: str | None,
        message: str,
    ) -> str:
        if error_kind == "timeout":
            return "model_timeout"
        if error_kind == "connection":
            return "model_connection_error"
        if status_code == 401:
            return "model_auth_error"
        if status_code == 403:
            return "model_permission_error"
        if status_code == 402 or cls._looks_like_quota_error(
            error_type,
            error_code,
            message,
        ):
            return "model_quota_error"
        if status_code == 429:
            return "model_rate_limit"
        if status_code == 400:
            return "model_bad_request"
        if status_code is not None and status_code >= 500:
            return "model_server_error"
        return "model_request_error"

    @classmethod
    def _is_recoverable_error(
        cls,
        *,
        status_code: int | None,
        error_kind: str | None,
        error_type: str | None,
        error_code: str | None,
        message: str,
    ) -> bool:
        if cls._looks_like_quota_error(error_type, error_code, message):
            return False
        if error_kind in {"timeout", "connection"}:
            return True
        if status_code == 429:
            return True
        if status_code in {408, 409}:
            return True
        if status_code is not None and status_code >= 500:
            return True
        return False

    @classmethod
    def _looks_like_quota_error(
        cls,
        error_type: str | None,
        error_code: str | None,
        message: str,
    ) -> bool:
        tokens = {
            cls._normalize_token(error_type),
            cls._normalize_token(error_code),
        }
        quota_tokens = {
            "insufficient_quota",
            "quota_exceeded",
            "quota_exhausted",
            "billing_hard_limit_reached",
            "payment_required",
            "insufficient_balance",
            "credit_balance_too_low",
        }
        if any(token in quota_tokens for token in tokens if token):
            return True

        lowered = message.lower()
        markers = (
            "insufficient quota",
            "quota exceeded",
            "quota exhausted",
            "billing hard limit",
            "payment required",
            "out of credits",
            "out of quota",
            "insufficient balance",
            "credit balance",
        )
        return any(marker in lowered for marker in markers)

    @classmethod
    def _extract_error_type_code(cls, payload: Any) -> tuple[str | None, str | None]:
        data: dict[str, Any] | None = None
        if isinstance(payload, dict):
            data = payload
        elif isinstance(payload, str) and payload.strip():
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed

        if not isinstance(data, dict):
            return None, None

        error_obj = data.get("error")
        type_value = data.get("type")
        code_value = data.get("code")
        if isinstance(error_obj, dict):
            type_value = error_obj.get("type") or type_value
            code_value = error_obj.get("code") or code_value

        return cls._normalize_token(type_value), cls._normalize_token(code_value)

    @classmethod
    def _extract_retry_after_from_headers(cls, headers: Any) -> float | None:
        if not headers:
            return None

        retry_ms = cls._header_value(headers, "retry-after-ms")
        if retry_ms is not None:
            try:
                value = float(retry_ms) / 1000.0
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                return value

        retry_after = cls._header_value(headers, "retry-after")
        if retry_after is None:
            return None

        text = str(retry_after).strip()
        if not text:
            return None
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return max(0.1, float(text))

        try:
            retry_at = parsedate_to_datetime(text)
        except Exception:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        remaining = (retry_at - datetime.now(retry_at.tzinfo)).total_seconds()
        return max(0.1, remaining)

    @staticmethod
    def _header_value(headers: Any, name: str) -> Any:
        if hasattr(headers, "get"):
            value = headers.get(name) or headers.get(name.title())
            if value is not None:
                return value
        if isinstance(headers, dict):
            for key, value in headers.items():
                if isinstance(key, str) and key.lower() == name.lower():
                    return value
        return None

    @staticmethod
    def _normalize_token(value: Any) -> str | None:
        if value is None:
            return None
        token = str(value).strip().lower()
        return token or None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)
