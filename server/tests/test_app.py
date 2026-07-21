import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from bumblehive.observability import make_event
from bumblehive.protocols.errors import AgentError
from bumblehive_server.app import create_app
from bumblehive_server.routes.chat import chat


@dataclass
class FakeResult:
    final_content: str = "Hello"
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(
        default_factory=lambda: {"completion_tokens": 1}
    )
    stop_reason: str = "completed"
    error: Any = None


class FakeStream:
    def __init__(self) -> None:
        self._events = [
            make_event(
                "model.stream.content_delta",
                run_id="run-1",
                session_id="session-1",
                delta="Hello",
            )
        ]

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for event in self._events:
            yield event

    async def result(self) -> FakeResult:
        return FakeResult()

    async def aclose(self) -> None:
        return None


class FakeRuntime:
    def stream(self, *_args: Any, **_kwargs: Any) -> FakeStream:
        return FakeStream()


class BlockingFakeStream:
    def __init__(self, session_id: str = "session-1") -> None:
        self.closed = False
        self.session_id = session_id

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        yield make_event(
            "model.stream.content_delta",
            run_id="run-cancel",
            session_id=self.session_id,
            delta="Partial",
        )
        await asyncio.Event().wait()

    async def result(self) -> FakeResult:
        raise AssertionError("cancelled stream must not produce a result")

    async def aclose(self) -> None:
        self.closed = True


class CancellableFakeRuntime:
    def __init__(self) -> None:
        self.blocking_stream = BlockingFakeStream()
        self.calls = 0

    def stream(self, *_args: Any, **_kwargs: Any) -> FakeStream | BlockingFakeStream:
        self.calls += 1
        if self.calls == 1:
            return self.blocking_stream
        return FakeStream()


class ParallelFakeRuntime:
    def __init__(self) -> None:
        self.streams: dict[str, BlockingFakeStream] = {}

    def stream(
        self,
        *_args: Any,
        session_id: str,
        **_kwargs: Any,
    ) -> BlockingFakeStream:
        stream = BlockingFakeStream(session_id)
        self.streams[session_id] = stream
        return stream


class FailingFakeStream:
    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        raise RuntimeError("simulated agent failure")
        yield

    async def result(self) -> FakeResult:
        raise AssertionError("failed stream must not produce a result")

    async def aclose(self) -> None:
        return None


class FailingFakeRuntime:
    def stream(self, *_args: Any, **_kwargs: Any) -> FailingFakeStream:
        return FailingFakeStream()


class ErrorResultFakeStream(FakeStream):
    async def result(self) -> FakeResult:
        return FakeResult(
            stop_reason="model_error",
            error=AgentError(
                code="model_error",
                message="do-not-log-this-error-message",
            ),
        )


class ErrorResultFakeRuntime:
    def stream(self, *_args: Any, **_kwargs: Any) -> ErrorResultFakeStream:
        return ErrorResultFakeStream()


class DisconnectingWebSocket:
    def __init__(self) -> None:
        self.app = SimpleNamespace(
            state=SimpleNamespace(runtime_service=FakeService())
        )

    async def accept(self) -> None:
        return None

    async def send_json(self, _payload: Any) -> None:
        return None

    async def receive_json(self) -> Any:
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(code=1000)


class FakeService:
    ready = True

    def __init__(self) -> None:
        self.runtime = FakeRuntime()
        self.settings = {
            "provider": {
                "type": "openai_chat_completions",
                "model": "test-model",
                "api_key_configured": False,
            }
        }

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def public_config(self) -> dict[str, Any]:
        return self.settings

    async def update_config(self, update: dict[str, Any]) -> None:
        self.settings.update(update)

    async def delete_session(self, _session_id: str) -> bool:
        return True

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[FakeRuntime]:
        yield self.runtime


class FakeSessionReader:
    async def list(self) -> list[Any]:
        return []

    async def get(self, session_id: str) -> Any:
        return SimpleNamespace(session_id=session_id, messages=[], updated_at=0.0)


def test_health_and_websocket_stream(caplog: Any) -> None:
    app = create_app(
        runtime_service=FakeService(),  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with TestClient(app) as client:
            health = client.get(
                "/api/v1/health",
                headers={"Origin": "http://127.0.0.1:1420"},
            )
            assert health.json() == {
                "status": "ok",
                "runtime": "ready",
            }
            assert health.headers["access-control-allow-origin"] == (
                "http://127.0.0.1:1420"
            )

            preflight = client.options(
                "/api/v1/settings",
                headers={
                    "Origin": "http://127.0.0.1:1420",
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == (
                "http://127.0.0.1:1420"
            )

            with client.websocket_connect("/ws/v1/chat/session-1") as websocket:
                assert websocket.receive_json()["type"] == "ready"
                websocket.send_json({"type": "message", "content": "Hi"})
                event = websocket.receive_json()
                result = websocket.receive_json()

            deleted = client.delete("/api/v1/sessions/session-1")

    assert event["kind"] == "model.stream.content_delta"
    assert event["payload"]["delta"] == "Hello"
    assert result["type"] == "result"
    assert result["final_content"] == "Hello"
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert "[lifecycle] startup completed | duration=" in caplog.text
    assert "[websocket] connected | session_id=session-1" in caplog.text
    assert "[agent] started | session_id=session-1" in caplog.text
    assert "stop_reason=completed | tokens=completion:1" in caplog.text
    assert "[lifecycle] shutdown completed | duration=" in caplog.text


def test_websocket_can_cancel_a_run_and_continue_on_the_same_connection(
    caplog: Any,
) -> None:
    service = FakeService()
    runtime = CancellableFakeRuntime()
    service.runtime = runtime  # type: ignore[assignment]
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/v1/chat/session-1") as websocket:
                assert websocket.receive_json()["type"] == "ready"
                websocket.send_json({"type": "message", "content": "Start"})
                assert websocket.receive_json()["payload"]["delta"] == "Partial"

                websocket.send_json({"type": "cancel"})
                cancelled = websocket.receive_json()
                assert cancelled == {
                    "type": "cancelled",
                    "session_id": "session-1",
                }

                websocket.send_json({"type": "message", "content": "Continue"})
                assert websocket.receive_json()["payload"]["delta"] == "Hello"
                assert websocket.receive_json()["type"] == "result"

    assert runtime.blocking_stream.closed is True
    assert "[agent] cancelled | session_id=session-1 | duration=" in caplog.text


def test_different_sessions_can_stream_in_parallel() -> None:
    service = FakeService()
    runtime = ParallelFakeRuntime()
    service.runtime = runtime  # type: ignore[assignment]
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/v1/chat/session-1") as first:
            assert first.receive_json()["type"] == "ready"
            first.send_json({"type": "message", "content": "First"})
            assert first.receive_json()["payload"]["delta"] == "Partial"

            with client.websocket_connect("/ws/v1/chat/session-2") as second:
                assert second.receive_json()["type"] == "ready"
                second.send_json({"type": "message", "content": "Second"})
                assert second.receive_json()["payload"]["delta"] == "Partial"

                first.send_json({"type": "cancel"})
                second.send_json({"type": "cancel"})
                assert first.receive_json()["type"] == "cancelled"
                assert second.receive_json()["type"] == "cancelled"

    assert set(runtime.streams) == {"session-1", "session-2"}
    assert all(stream.closed for stream in runtime.streams.values())


def test_agent_failure_logs_traceback_without_prompt(caplog: Any) -> None:
    service = FakeService()
    service.runtime = FailingFakeRuntime()  # type: ignore[assignment]
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/v1/chat/session-1") as websocket:
                assert websocket.receive_json()["type"] == "ready"
                websocket.send_json(
                    {
                        "type": "message",
                        "content": "do-not-log-this-prompt",
                    }
                )
                error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "runtime_error"
    failure_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("[agent] failed")
    ]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is not None
    assert "do-not-log-this-prompt" not in caplog.text


def test_websocket_disconnect_logs_duration(caplog: Any) -> None:
    websocket = DisconnectingWebSocket()

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        asyncio.run(chat(websocket, "session-1"))  # type: ignore[arg-type]

    assert "[websocket] connected | session_id=session-1" in caplog.text
    assert (
        "[websocket] disconnected | session_id=session-1 | duration="
        in caplog.text
    )


def test_agent_error_result_logs_code_without_error_message(caplog: Any) -> None:
    service = FakeService()
    service.runtime = ErrorResultFakeRuntime()  # type: ignore[assignment]
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/v1/chat/session-1") as websocket:
                assert websocket.receive_json()["type"] == "ready"
                websocket.send_json({"type": "message", "content": "Hi"})
                assert websocket.receive_json()["type"] == "event"
                result = websocket.receive_json()

    assert result["type"] == "result"
    assert result["error"]["code"] == "model_error"
    assert "[agent] failed | session_id=session-1" in caplog.text
    assert "stop_reason=model_error | error_code=model_error" in caplog.text
    assert "do-not-log-this-error-message" not in caplog.text
