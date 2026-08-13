import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from inspect import isawaitable
from typing import Any

from ..protocols import Message
from ..protocols.errors import AgentError
from ..protocols.generation import GenerationConfig
from ..protocols.tool_calls import ToolCall, parse_tool_call
from .base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamCallbacks,
)


_STREAM_IDLE_TIMEOUT_S = 90.0
_ALLOWED_MESSAGE_KEYS = frozenset(
    {
        "role",
        "content",
        "tool_calls",
        "tool_call_id",
        "name",
        "reasoning_content",
    }
)
_NON_RECOVERABLE_QUOTA_TOKENS = frozenset(
    {
        "insufficient_quota",
        "quota_exceeded",
        "quota_exhausted",
        "billing_hard_limit_reached",
        "billing_not_active",
        "payment_required",
        "insufficient_balance",
        "credit_balance_too_low",
    }
)
_NON_RECOVERABLE_QUOTA_MARKERS = (
    "insufficient_quota",
    "insufficient quota",
    "quota exceeded",
    "quota exhausted",
    "billing hard limit",
    "billing_hard_limit_reached",
    "billing not active",
    "insufficient balance",
    "insufficient_balance",
    "credit balance too low",
    "payment required",
    "out of credits",
    "out of quota",
    "exceeded your current quota",
)


@dataclass(frozen=True, slots=True)
class _ParsedStreamChunk:
    content_delta: str = ""
    refusal_delta: str = ""
    reasoning_delta: str = ""
    tool_call_deltas: list[dict[str, Any]] = field(default_factory=list)


class OpenAIChatCompletionsProvider(ModelProvider):
    """Provider for OpenAI-compatible Chat Completions APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_generation: GenerationConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.default_generation = default_generation or GenerationConfig()
        self._client = client

    async def generate(self, request: ModelRequest) -> ModelResponse:
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

    async def generate_stream(
        self,
        request: ModelRequest,
        *,
        callbacks: ModelStreamCallbacks | None = None,
    ) -> ModelResponse:
        payload = self._build_payload(request)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        idle_timeout_s = _STREAM_IDLE_TIMEOUT_S
        accumulator = _ChatStreamAccumulator(type(self))
        try:
            stream = await self._create_stream(payload)
            stream_iter = stream.__aiter__()
        except asyncio.TimeoutError:
            return self._stream_idle_timeout_response(idle_timeout_s)
        except Exception as exc:
            return self._error_response_from_exception(exc)

        while True:
            try:
                chunk = await asyncio.wait_for(
                    stream_iter.__anext__(),
                    timeout=idle_timeout_s,
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                return self._stream_idle_timeout_response(idle_timeout_s)
            except Exception as exc:
                return self._error_response_from_exception(exc)

            try:
                parsed_chunk = accumulator.consume(chunk)
            except Exception as exc:
                return self._stream_parse_error_response(exc)

            await self._emit_parsed_stream_callbacks(parsed_chunk, callbacks)

        try:
            return accumulator.finalize()
        except Exception as exc:
            return self._stream_parse_error_response(exc)

    @staticmethod
    def _stream_idle_timeout_response(idle_timeout_s: float) -> ModelResponse:
        message = f"stream stalled for more than {idle_timeout_s:g} seconds"
        return ModelResponse(
            content=f"Error calling model: {message}",
            finish_reason="error",
            error=AgentError(
                code="model_timeout",
                message=message,
                recoverable=True,
            ),
            error_kind="timeout",
        )

    @staticmethod
    def _stream_parse_error_response(exc: Exception) -> ModelResponse:
        return ModelResponse(
            content=f"Error parsing model stream response: {exc}",
            finish_reason="error",
            error=AgentError(
                code="model_response_parse_error",
                message=str(exc),
            ),
        )

    async def _create_stream(self, payload: dict[str, Any]) -> Any:
        completions = self._client_or_create().chat.completions
        try:
            return await completions.create(**payload)
        except Exception as exc:
            if not self._should_retry_stream_without_options(exc):
                raise

        fallback_payload = dict(payload)
        fallback_payload.pop("stream_options", None)
        return await completions.create(**fallback_payload)

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
            "model": request.model,
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
        payload["max_completion_tokens"] = (
            generation.effective_max_completion_tokens
        )
        if generation.temperature is not None:
            payload["temperature"] = generation.temperature
        if generation.reasoning_effort is not None:
            payload["reasoning_effort"] = generation.reasoning_effort
        if generation.extra_body is not None:
            payload["extra_body"] = generation.extra_body

    @staticmethod
    def _sanitize_messages(messages: list[Message]) -> list[Message]:
        sanitized: list[Message] = []
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
    async def _emit_parsed_stream_callbacks(
        parsed_chunk: _ParsedStreamChunk,
        callbacks: ModelStreamCallbacks | None,
    ) -> None:
        if callbacks is None:
            return

        if parsed_chunk.content_delta and callbacks.on_content_delta:
            await callbacks.on_content_delta(parsed_chunk.content_delta)

        if parsed_chunk.refusal_delta and callbacks.on_refusal_delta:
            await callbacks.on_refusal_delta(parsed_chunk.refusal_delta)

        if parsed_chunk.reasoning_delta and callbacks.on_reasoning_delta:
            await callbacks.on_reasoning_delta(parsed_chunk.reasoning_delta)

        if callbacks.on_tool_call_delta:
            for tool_delta in parsed_chunk.tool_call_deltas:
                await callbacks.on_tool_call_delta(tool_delta)

    @classmethod
    def _accumulate_tool_delta(
        cls,
        tool_buffers: dict[int, dict[str, str]],
        tool_delta: Any,
        index_hint: int,
    ) -> None:
        tool_index = cls._get(tool_delta, "index")
        index = tool_index if isinstance(tool_index, int) else index_hint
        buffer = tool_buffers.setdefault(
            index,
            {
                "id": "",
                "name": "",
                "arguments": "",
            },
        )

        call_id = cls._get(tool_delta, "id")
        if call_id:
            buffer["id"] = str(call_id)

        function = cls._get(tool_delta, "function")
        if function is None:
            return

        name = cls._get(function, "name")
        if name:
            buffer["name"] = str(name)
        arguments = cls._get(function, "arguments")
        if arguments:
            buffer["arguments"] += str(arguments)

    @classmethod
    def _parse_stream_tool_calls(
        cls,
        tool_buffers: dict[int, dict[str, str]],
    ) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for index in sorted(tool_buffers):
            buffer = tool_buffers[index]
            if not buffer["name"]:
                continue
            tool_calls.append(
                parse_tool_call(
                    {
                        "id": buffer["id"] or f"call_{index}",
                        "function": {
                            "name": buffer["name"],
                            "arguments": buffer["arguments"] or "{}",
                        },
                    }
                )
            )
        return tool_calls

    @classmethod
    def _stream_choice(cls, chunk: Any) -> Any:
        choices = cls._get(chunk, "choices")
        if not choices:
            return None
        return choices[0]

    @classmethod
    def _extract_text(cls, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    @classmethod
    def _should_retry_stream_without_options(cls, exc: Exception) -> bool:
        metadata = cls._extract_error_metadata(exc)
        if metadata["error_status_code"] not in {400, 422}:
            return False

        message = cls._format_error_message(exc).lower()
        if "stream_options" not in message and "stream options" not in message:
            return False

        markers = (
            "unknown",
            "unsupported",
            "unrecognized",
            "invalid",
            "extra",
            "not permitted",
            "not allowed",
        )
        return any(marker in message for marker in markers)

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
                error_should_retry=metadata["error_should_retry"],
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
            "error_should_retry": cls._extract_should_retry(headers),
            "retry_after": (
                cls._extract_retry_after_from_headers(headers)
                or cls._extract_retry_after_from_text(cls._format_error_message(exc))
            ),
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
            status_code=status_code,
            error_type=error_type,
            error_code=error_code,
            message=message,
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
        error_should_retry: bool | None,
        message: str,
    ) -> bool:
        if error_should_retry is not None:
            return error_should_retry
        if cls._looks_like_quota_error(
            status_code=status_code,
            error_type=error_type,
            error_code=error_code,
            message=message,
        ):
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
        *,
        status_code: int | None,
        error_type: str | None,
        error_code: str | None,
        message: str,
    ) -> bool:
        tokens = {
            cls._normalize_token(error_type),
            cls._normalize_token(error_code),
        }
        if any(token in _NON_RECOVERABLE_QUOTA_TOKENS for token in tokens if token):
            return True

        if status_code not in {402, 429}:
            return False

        lowered = message.lower()
        return any(marker in lowered for marker in _NON_RECOVERABLE_QUOTA_MARKERS)

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

    @classmethod
    def _extract_retry_after_from_text(cls, text: str) -> float | None:
        lowered = text.lower()
        patterns = (
            r"retry after\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)?",
            r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)",
            r"wait\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)\s*before retry",
            r"retry[_-]?after[\"'\s:=]+(\d+(?:\.\d+)?)",
        )
        for index, pattern in enumerate(patterns):
            match = re.search(pattern, lowered)
            if not match:
                continue
            value = float(match.group(1))
            unit = match.group(2) if index < 3 else "s"
            return cls._retry_after_seconds(value, unit)
        return None

    @staticmethod
    def _retry_after_seconds(value: float, unit: str | None) -> float:
        normalized = (unit or "s").lower()
        if normalized in {"ms", "milliseconds"}:
            return max(0.1, value / 1000.0)
        if normalized in {"m", "min", "minutes"}:
            return max(0.1, value * 60.0)
        return max(0.1, value)

    @classmethod
    def _extract_should_retry(cls, headers: Any) -> bool | None:
        raw = cls._header_value(headers, "x-should-retry")
        if not isinstance(raw, str):
            return None
        lowered = raw.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return None

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


@dataclass(slots=True)
class _ChatStreamAccumulator:
    provider_cls: Any
    content_parts: list[str] = field(default_factory=list)
    refusal_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    tool_buffers: dict[int, dict[str, str]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)

    def consume(self, chunk: Any) -> _ParsedStreamChunk:
        parsed_usage = self.provider_cls._parse_usage(
            self.provider_cls._get(chunk, "usage")
        )
        if parsed_usage:
            self.usage = parsed_usage

        choice = self.provider_cls._stream_choice(chunk)
        if choice is None:
            return _ParsedStreamChunk()

        raw_finish_reason = self.provider_cls._get(choice, "finish_reason")
        if raw_finish_reason:
            self.finish_reason = str(raw_finish_reason)

        delta = self.provider_cls._get(choice, "delta")
        if delta is None:
            return _ParsedStreamChunk()

        content_delta = self.provider_cls._extract_text(
            self.provider_cls._get(delta, "content")
        )
        if content_delta:
            self.content_parts.append(content_delta)

        refusal_delta = self.provider_cls._extract_text(
            self.provider_cls._get(delta, "refusal")
        )
        if refusal_delta:
            self.refusal_parts.append(refusal_delta)

        reasoning_delta = (
            self.provider_cls._extract_text(
                self.provider_cls._get(delta, "reasoning_content")
            )
            or self.provider_cls._extract_text(
                self.provider_cls._get(delta, "reasoning")
            )
        )
        if reasoning_delta:
            self.reasoning_parts.append(reasoning_delta)

        tool_call_deltas: list[dict[str, Any]] = []
        for index, tool_delta in enumerate(
            self.provider_cls._get(delta, "tool_calls") or []
        ):
            self.provider_cls._accumulate_tool_delta(
                self.tool_buffers,
                tool_delta,
                index,
            )
            tool_call_deltas.append(self._tool_call_delta_payload(tool_delta, index))

        return _ParsedStreamChunk(
            content_delta=content_delta,
            refusal_delta=refusal_delta,
            reasoning_delta=reasoning_delta,
            tool_call_deltas=tool_call_deltas,
        )

    def finalize(self) -> ModelResponse:
        if self.finish_reason is None:
            message = (
                "model stream ended without a final finish_reason chunk; "
                "the response may have been interrupted or truncated"
            )
            return ModelResponse(
                content=self._joined(self.content_parts),
                finish_reason="error",
                usage=self.usage,
                refusal=self._joined(self.refusal_parts),
                reasoning_content=self._joined(self.reasoning_parts),
                error=AgentError(
                    code="model_stream_incomplete",
                    message=message,
                    recoverable=True,
                ),
                error_kind="stream_incomplete",
            )

        return ModelResponse(
            content=self._joined(self.content_parts),
            tool_calls=self.provider_cls._parse_stream_tool_calls(self.tool_buffers),
            finish_reason=self.finish_reason,
            usage=self.usage,
            refusal=self._joined(self.refusal_parts),
            reasoning_content=self._joined(self.reasoning_parts),
        )

    def _tool_call_delta_payload(
        self,
        tool_delta: Any,
        index_hint: int,
    ) -> dict[str, Any]:
        function = self.provider_cls._get(tool_delta, "function")
        tool_index = self.provider_cls._get(tool_delta, "index")
        return {
            "index": tool_index if tool_index is not None else index_hint,
            "call_id": str(self.provider_cls._get(tool_delta, "id") or ""),
            "name": (
                str(self.provider_cls._get(function, "name") or "")
                if function is not None
                else ""
            ),
            "arguments_delta": (
                str(self.provider_cls._get(function, "arguments") or "")
                if function is not None
                else ""
            ),
        }

    @staticmethod
    def _joined(parts: list[str]) -> str | None:
        return "".join(parts) or None
