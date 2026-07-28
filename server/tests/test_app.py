import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bumblehive.observability.events import make_event
from bumblehive.protocols.errors import AgentError
from bumblehive_server.app import create_app
from bumblehive_server.chat.frames import (
    result_frame as _result_frame,
    ui_event_frame as _ui_event_frame,
)
from bumblehive_server.chat.streaming import (
    WebSocketSubagentObserver as _WebSocketSubagentObserver,
    persist_run_duration as _persist_run_duration,
)
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
                "model.request.started",
                run_id="run-1",
                session_id="session-1",
                request={
                    "messages": [{"role": "user", "content": "internal prompt"}]
                },
            ),
            make_event(
                "model.stream.content_delta",
                run_id="run-1",
                session_id="session-1",
                delta="Hello",
            ),
            make_event(
                "model.response.finished",
                run_id="run-1",
                session_id="session-1",
                message={"role": "assistant", "content": "Hello"},
            ),
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


class RecordingWebSocket:
    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []

    async def send_json(self, frame: dict[str, Any]) -> None:
        self.frames.append(frame)


@pytest.mark.asyncio
async def test_subagent_observer_reuses_existing_websocket_frames() -> None:
    websocket = RecordingWebSocket()
    observer = _WebSocketSubagentObserver(
        websocket,  # type: ignore[arg-type]
        SimpleNamespace(),
    )

    await observer.on_created(
        session_id="child-session",
        workspace="/tmp/workspace",
        title="Inspect project",
        content="Inspect the project",
    )
    await observer.on_event(
        make_event(
            "model.stream.content_delta",
            run_id="child-run",
            session_id="child-session",
            delta="Partial",
        )
    )
    await observer.on_result(
        session_id="child-session",
        result=FakeResult(final_content="Complete"),  # type: ignore[arg-type]
        duration_s=1.25,
    )

    assert websocket.frames[0] == {
        "type": "session_created",
        "session_id": "child-session",
        "workspace": "/tmp/workspace",
        "title": "Inspect project",
        "content": "Inspect the project",
    }
    assert websocket.frames[1]["type"] == "event"
    assert websocket.frames[1]["session_id"] == "child-session"
    assert websocket.frames[1]["payload"] == {"delta": "Partial"}
    assert websocket.frames[2] == _result_frame(
        "child-session",
        FakeResult(final_content="Complete"),  # type: ignore[arg-type]
        1.25,
    )


def test_ui_event_filter_removes_unused_and_large_payloads() -> None:
    internal = make_event(
        "model.request.started",
        run_id="run-1",
        request={"messages": [{"role": "user", "content": "private prompt"}]},
    )
    assert _ui_event_frame(internal) is None

    tool_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        tool_result={
            "role": "tool",
            "tool_call_id": "call-1",
            "name": "read_file",
            "content": "large tool output",
        },
        duration_s=0.25,
    )
    tool_frame = _ui_event_frame(tool_finished)
    assert tool_frame is not None
    assert tool_frame["payload"] == {
        "ok": True,
        "tool_result": {
            "tool_call_id": "call-1",
            "name": "read_file",
            "detail": {"kind": "read"},
        },
        "duration_s": 0.25,
    }

    response_without_reasoning = make_event(
        "model.response.finished",
        run_id="run-1",
        message={"role": "assistant", "content": "answer"},
    )
    assert _ui_event_frame(response_without_reasoning) is None

    response_with_reasoning = make_event(
        "model.response.finished",
        run_id="run-1",
        message={
            "role": "assistant",
            "content": "answer",
            "reasoning_content": "reasoning",
        },
    )
    reasoning_frame = _ui_event_frame(response_with_reasoning)
    assert reasoning_frame is not None
    assert reasoning_frame["payload"] == {
        "message": {"reasoning_content": "reasoning"}
    }


def test_ui_event_filter_builds_bounded_tool_details() -> None:
    shell_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        tool_result={
            "role": "tool",
            "tool_call_id": "call-shell",
            "name": "exec",
            "content": json.dumps(
                {
                    "command": "npm run build",
                    "working_dir": "/tmp/workspace",
                    "exit_code": 0,
                    "stdout": "x" * 20_000,
                    "stderr": "",
                    "stdout_truncated_chars": 12,
                }
            ),
        },
        duration_s=1.25,
    )

    shell_frame = _ui_event_frame(shell_finished)

    assert shell_frame is not None
    shell_result = shell_frame["payload"]["tool_result"]
    assert shell_result["name"] == "exec"
    assert shell_result["detail"]["kind"] == "shell"
    assert shell_result["detail"]["command"] == "npm run build"
    assert "已省略" in shell_result["detail"]["stdout"]
    assert shell_result["detail"]["truncatedCharacters"] == 4_012
    assert "x" * 20_000 not in str(shell_frame)

    mutation_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        file_changes=[
            {
                "path": "webui/src/App.tsx",
                "added": 8,
                "deleted": 6,
                "unified_diff": (
                    "--- webui/src/App.tsx\n"
                    "+++ webui/src/App.tsx\n"
                    "@@ -117,7 +117,9 @@\n"
                    " context\n"
                    "-old\n"
                    "+new"
                ),
            }
        ],
        tool_result={
            "role": "tool",
            "tool_call_id": "call-patch",
            "name": "apply_patch",
            "content": json.dumps(
                {
                    "success": True,
                    "dry_run": False,
                    "edits": [
                        {
                            "action": "replace",
                            "path": "webui/src/App.tsx",
                            "added": 8,
                            "deleted": 6,
                        }
                    ],
                }
            ),
        },
    )

    mutation_frame = _ui_event_frame(mutation_finished)

    assert mutation_frame is not None
    assert mutation_frame["payload"]["tool_result"]["detail"] == {
        "kind": "mutation",
        "dryRun": False,
        "fileChanges": [
            {
                "path": "webui/src/App.tsx",
                "added": 8,
                "deleted": 6,
                "unifiedDiff": (
                    "--- webui/src/App.tsx\n"
                    "+++ webui/src/App.tsx\n"
                    "@@ -117,7 +117,9 @@\n"
                    " context\n"
                    "-old\n"
                    "+new"
                ),
            }
        ],
    }

    read_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        tool_result={
            "role": "tool",
            "tool_call_id": "call-grep",
            "name": "grep",
            "content": json.dumps(
                {
                    "total_matches": 7,
                    "files": [
                        "webui/src/App.tsx",
                        "webui/src/components/ChatView.tsx",
                    ],
                    "truncated": False,
                    "matches": [
                        {
                            "path": "webui/src/App.tsx",
                            "line": 10,
                            "text": "private matching content",
                        }
                    ],
                }
            ),
        },
    )

    read_frame = _ui_event_frame(read_finished)

    assert read_frame is not None
    assert read_frame["payload"]["tool_result"]["detail"] == {
        "kind": "read",
        "totalMatches": 7,
        "truncated": False,
        "items": [
            "webui/src/App.tsx",
            "webui/src/components/ChatView.tsx",
        ],
    }
    assert "private matching content" not in str(read_frame)


def test_ui_event_filter_promotes_builtin_result_errors() -> None:
    tool_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        tool_result={
            "role": "tool",
            "tool_call_id": "call-1",
            "name": "read_file",
            "content": json.dumps({"error": "path does not exist"}),
        },
    )

    tool_frame = _ui_event_frame(tool_finished)

    assert tool_frame is not None
    assert tool_frame["payload"]["ok"] is False
    assert tool_frame["payload"]["error"]["message"] == "path does not exist"


def test_ui_event_filter_builds_bounded_exec_session_details() -> None:
    sessions = [
        {
            "session_id": f"session-{index}-" + "s" * 400,
            "command": "python task.py " + "x" * 5_000,
            "working_dir": "/tmp/" + "workspace/" * 200,
            "running": True,
            "exit_code": None,
            "elapsed_seconds": 12.5,
            "idle_seconds": 1.25,
            "remaining_seconds": None,
        }
        for index in range(25)
    ]
    tool_finished = make_event(
        "tool.call.finished",
        run_id="run-1",
        ok=True,
        tool_result={
            "role": "tool",
            "tool_call_id": "call-sessions",
            "name": "list_exec_sessions",
            "content": json.dumps({"sessions": sessions}),
        },
    )

    tool_frame = _ui_event_frame(tool_finished)

    assert tool_frame is not None
    detail = tool_frame["payload"]["tool_result"]["detail"]
    assert detail["kind"] == "shellSessions"
    assert len(detail["sessions"]) == 20
    first = detail["sessions"][0]
    assert len(first["sessionId"]) == 300
    assert len(first["command"]) == 4_000
    assert len(first["workingDirectory"]) == 1_000
    assert first["running"] is True
    assert first["exitCode"] is None
    assert first["elapsedSeconds"] == 12.5
    assert first["idleSeconds"] == 1.25
    assert first["remainingSeconds"] is None


@pytest.mark.asyncio
async def test_run_duration_is_persisted_on_the_final_assistant_message() -> None:
    class FakeSessions:
        def __init__(self) -> None:
            self.messages = [
                {"role": "user", "content": "task"},
                {"role": "assistant", "content": None, "tool_calls": []},
                {"role": "assistant", "content": "done"},
            ]
            self.session = SimpleNamespace(lock=asyncio.Lock())

        async def get(self, _session_id: str) -> Any:
            return self.session

        def get_history(self, _session: Any) -> list[dict[str, Any]]:
            return [dict(message) for message in self.messages]

        async def replace_and_save(
            self,
            _session: Any,
            messages: list[dict[str, Any]],
        ) -> None:
            self.messages = messages

    sessions = FakeSessions()
    runtime = SimpleNamespace(sessions=sessions)

    await _persist_run_duration(runtime, "session-1", 12.3456)

    assert "_bumblehive_ui" not in sessions.messages[1]
    assert sessions.messages[2]["_bumblehive_ui"] == {
        "duration_s": 12.346
    }


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
        self.workspace = Path("/tmp/workspace")
        self.model_requests: list[Any] = []
        self.deleted_sessions: list[str] = []
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

    async def list_models(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
    ) -> list[str]:
        self.model_requests.append({"base_url": base_url, "api_key": api_key})
        return ["test-model", "other-model"]

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[FakeRuntime]:
        yield self.runtime


class FakeSessionReader:
    def __init__(self) -> None:
        self.created_workspaces: list[Any] = []
        self.migrated_workspaces: list[Any] = []
        self.deleted_metadata: list[str] = []
        self.descendants: dict[str, list[str]] = {}

    async def create(
        self,
        workspace: Any,
    ) -> str:
        self.created_workspaces.append(workspace)
        return "created-session"

    async def migrate_missing_workspace(self, workspace: Any) -> int:
        self.migrated_workspaces.append(workspace)
        return 0

    async def delete_metadata(self, session_id: str) -> bool:
        self.deleted_metadata.append(session_id)
        return True

    async def descendant_ids(self, session_id: str) -> list[str]:
        return self.descendants.get(session_id, [])

    async def list(self) -> list[Any]:
        return []

    async def get(self, session_id: str) -> Any:
        return SimpleNamespace(
            session_id=session_id,
            workspace="/tmp/workspace",
            messages=[],
            created_at=0.0,
            updated_at=0.0,
        )


def test_create_session_uses_current_workspace() -> None:
    service = FakeService()
    reader = FakeSessionReader()
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=reader,  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/sessions")
        selected_workspace_response = client.post(
            "/api/v1/sessions",
            json={"workspace": "/tmp/selected-workspace"},
        )
        blank_workspace_response = client.post(
            "/api/v1/sessions",
            json={"workspace": "   "},
        )
        deleted = client.delete("/api/v1/sessions/created-session")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "created-session",
        "workspace": str(service.workspace),
    }
    assert selected_workspace_response.status_code == 200
    assert selected_workspace_response.json() == {
        "session_id": "created-session",
        "workspace": str(Path("/tmp/selected-workspace").resolve()),
    }
    assert blank_workspace_response.status_code == 422
    assert reader.created_workspaces == [
        service.workspace,
        Path("/tmp/selected-workspace").resolve(),
    ]
    assert reader.migrated_workspaces == [service.workspace]
    assert deleted.json() == {
        "deleted": True,
        "deleted_session_ids": ["created-session"],
    }
    assert service.deleted_sessions == ["created-session"]
    assert reader.deleted_metadata == ["created-session"]


def test_delete_session_cascades_to_descendants() -> None:
    service = FakeService()
    reader = FakeSessionReader()
    reader.descendants["parent-session"] = [
        "child-session",
        "grandchild-session",
    ]
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=reader,  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        deleted = client.delete("/api/v1/sessions/parent-session")

    assert deleted.status_code == 200
    assert deleted.json() == {
        "deleted": True,
        "deleted_session_ids": [
            "grandchild-session",
            "child-session",
            "parent-session",
        ],
    }
    assert service.deleted_sessions == [
        "grandchild-session",
        "child-session",
        "parent-session",
    ]
    assert reader.deleted_metadata == service.deleted_sessions


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
    assert result["session_id"] == "session-1"
    assert result["final_content"] == "Hello"
    assert deleted.status_code == 200
    assert deleted.json() == {
        "deleted": True,
        "deleted_session_ids": ["session-1"],
    }
    assert "[lifecycle] startup completed | duration=" in caplog.text
    assert "[websocket] connected | session_id=session-1" in caplog.text
    assert "[agent] started | session_id=session-1" in caplog.text
    assert "stop_reason=completed | tokens=completion:1" in caplog.text
    assert "[lifecycle] shutdown completed | duration=" in caplog.text


def test_model_list_endpoint_accepts_flat_request() -> None:
    service = FakeService()
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/models",
            json={
                "api_key": "temporary-secret",
                "base_url": "https://draft.example/v1",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"models": ["test-model", "other-model"]}
    assert service.model_requests == [
        {
            "api_key": "temporary-secret",
            "base_url": "https://draft.example/v1",
        }
    ]


def test_model_list_endpoint_maps_validation_and_provider_errors() -> None:
    from bumblehive_server.runtime_service import ModelListError

    service = FakeService()
    app = create_app(
        runtime_service=service,  # type: ignore[arg-type]
        session_reader=FakeSessionReader(),  # type: ignore[arg-type]
    )

    async def reject_new_url(**_kwargs: Any) -> list[str]:
        raise ValueError("API Key is required when querying a different Base URL")

    service.list_models = reject_new_url  # type: ignore[method-assign]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/models",
            json={"base_url": "https://new.example/v1"},
        )
    assert response.status_code == 422

    async def fail_provider(**_kwargs: Any) -> list[str]:
        raise ModelListError("third-party model query failed")

    service.list_models = fail_provider  # type: ignore[method-assign]
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/models",
            json={
                "base_url": "https://new.example/v1",
                "api_key": "temporary-secret",
            },
        )
    assert response.status_code == 502


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
