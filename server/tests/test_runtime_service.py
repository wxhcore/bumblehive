import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from bumblehive import BumblehiveConfig, SkillsManager
from bumblehive.config import ProviderConfig
from bumblehive.observability.events import make_event
from bumblehive.protocols import ToolCall
from bumblehive.protocols.errors import AgentError
from bumblehive.tools import PathAllowlist, ToolManager
from bumblehive.tools.scope import (
    bind_tool_path_scope,
    bind_tool_session,
    reset_tool_path_scope,
    reset_tool_session,
)
from bumblehive_server.runtime_service import RuntimeBusyError, RuntimeService
from bumblehive_server.subagents import observe_subagents


class FakeRuntime:
    def __init__(
        self,
        config: BumblehiveConfig,
        *,
        initialize_error: Exception | None = None,
    ) -> None:
        self.config = config
        self.initialize_error = initialize_error
        self.initialize_calls = 0
        self.initialized = False
        self.closed = False
        self.deleted_sessions: list[str] = []

    async def initialize_tools(self) -> None:
        self.initialize_calls += 1
        if self.initialize_error is not None:
            raise self.initialize_error
        self.initialized = True

    async def close(self) -> None:
        self.closed = True

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True


class FakeModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    async def list(self) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


class FakeOpenAIClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeOpenAIClientFactory:
    def __init__(self, models: FakeModels) -> None:
        self.models = models
        self.calls: list[dict[str, str]] = []
        self.clients: list[FakeOpenAIClient] = []

    def __call__(self, *, api_key: str, base_url: str) -> FakeOpenAIClient:
        self.calls.append({"api_key": api_key, "base_url": base_url})
        client = FakeOpenAIClient(self.models)
        self.clients.append(client)
        return client


class RecordingSessionReader:
    def __init__(self, session_id: str = "child-session") -> None:
        self.session_id = session_id
        self.created_workspaces: list[Any] = []
        self.created_titles: list[str | None] = []
        self.created_parent_session_ids: list[str | None] = []

    async def create_child(
        self,
        workspace: Any,
        *,
        title: str,
        parent_session_id: str,
    ) -> str:
        self.created_workspaces.append(workspace)
        self.created_titles.append(title)
        self.created_parent_session_ids.append(parent_session_id)
        return self.session_id


class SequentialSessionReader(RecordingSessionReader):
    async def create_child(
        self,
        workspace: Any,
        *,
        title: str,
        parent_session_id: str,
    ) -> str:
        self.created_workspaces.append(workspace)
        self.created_titles.append(title)
        self.created_parent_session_ids.append(parent_session_id)
        return f"child-session-{len(self.created_workspaces)}"


class RecordingSubagentObserver:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.events: list[Any] = []
        self.results: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []
        self.cancelled: list[str] = []

    async def on_created(
        self,
        *,
        session_id: str,
        workspace: str,
        title: str,
        content: str,
    ) -> None:
        self.created.append(
            {
                "session_id": session_id,
                "workspace": workspace,
                "title": title,
                "content": content,
            }
        )

    async def on_event(self, event: Any) -> None:
        self.events.append(event)

    async def on_result(
        self,
        *,
        session_id: str,
        result: Any,
        duration_s: float,
    ) -> None:
        self.results.append(
            {
                "session_id": session_id,
                "result": result,
                "duration_s": duration_s,
            }
        )

    async def on_error(self, *, session_id: str, message: str) -> None:
        self.errors.append({"session_id": session_id, "message": message})

    async def on_cancelled(self, *, session_id: str) -> None:
        self.cancelled.append(session_id)


class SubagentFakeStream:
    def __init__(
        self,
        runtime: "SubagentFakeRuntime",
        session_id: str,
    ) -> None:
        self.runtime = runtime
        self.session_id = session_id

    def __aiter__(self) -> Any:
        return self._iterate()

    async def _iterate(self) -> Any:
        yield make_event(
            "model.stream.content_delta",
            run_id=f"run-{self.session_id}",
            session_id=self.session_id,
            delta=f"Streaming {self.session_id}",
        )
        await self.runtime.run_release.wait()
        if self.runtime.run_exception is not None:
            raise self.runtime.run_exception

    async def result(self) -> Any:
        return self.runtime.run_result

    async def aclose(self) -> None:
        return None


class SubagentFakeRuntime(FakeRuntime):
    def __init__(self, config: BumblehiveConfig) -> None:
        super().__init__(config)
        self.tools = ToolManager()
        self.run_started = asyncio.Event()
        self.run_release = asyncio.Event()
        self.expected_run_count = 1
        self.run_calls: list[dict[str, Any]] = []
        self.run_result = SimpleNamespace(final_content="Child answer", error=None)
        self.run_exception: Exception | None = None

    def stream(
        self,
        message: str,
        *,
        session_id: str,
        config: dict[str, Any],
    ) -> SubagentFakeStream:
        self.run_calls.append(
            {
                "message": message,
                "session_id": session_id,
                "config": config,
            }
        )
        if len(self.run_calls) >= self.expected_run_count:
            self.run_started.set()
        return SubagentFakeStream(self, session_id)


def _start_subagent_tool(
    runtime: SubagentFakeRuntime,
    *,
    workspace: Any,
    title: str,
    task: str,
) -> asyncio.Task[str]:
    session_token = bind_tool_session("parent-session")
    path_token = bind_tool_path_scope(workspace, PathAllowlist())
    try:
        tool = runtime.tools.get_tool("sub_agent")
        assert tool is not None
        return asyncio.create_task(tool.execute(title=title, task=task))
    finally:
        reset_tool_path_scope(path_token)
        reset_tool_session(session_token)


@pytest.mark.asyncio
async def test_runtime_service_starts_without_a_config_file(
    tmp_path,
    caplog,
) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "missing.json", runtime_factory=factory)

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        await service.startup()
        deleted = await service.delete_session("session-1")

    assert service.ready is True
    assert runtimes[0].initialized is True
    assert runtimes[0].initialize_calls == 1
    assert deleted is True
    assert service.config.provider.model is None
    assert service.public_config()["provider"] == {
        "type": "openai_chat_completions",
        "api_key_configured": False,
    }
    assert service.public_config()["generation"] == {
        "max_completion_tokens": 16_384,
    }
    assert service.public_config()["runtime"] == {
        "workspace": str(service.workspace),
        "context_window_tokens": 200_000,
        "max_tool_result_chars": 20_000,
        "max_iterations": 300,
    }
    assert service.public_config()["agent"] == {}
    assert service.public_config()["mcp_servers"] == []
    assert "[config] loaded | source=defaults | duration=" in caplog.text
    assert (
        "[session] delete completed | session_id=session-1 | deleted=true"
        in caplog.text
    )

    await service.shutdown()
    assert runtimes[0].closed is True


@pytest.mark.asyncio
async def test_runtime_service_updates_config_without_exposing_api_key(
    tmp_path,
    caplog,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(model="old-model", api_key="secret")
    ).to_json_file(config_path)
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(config_path, runtime_factory=factory)
    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        await service.startup()

        public = service.public_config()
        assert "api_key" not in public["provider"]
        assert public["provider"]["api_key_configured"] is True

        await service.update_config({"provider": {"model": "new-model"}})
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved == {
        "provider": {
            "type": "openai_chat_completions",
            "model": "new-model",
            "api_key": "secret",
            "base_url": None,
        },
        "generation": {
            "max_completion_tokens": 16_384,
            "temperature": None,
            "reasoning_effort": None,
            "extra_body": None,
        },
        "agent": {
            "instructions": None,
            "dynamic_context": {},
            "skill_names": None,
            "tool_names": None,
        },
        "runtime": {
            "workspace": None,
            "timezone": None,
            "context_window_tokens": 200_000,
            "max_tool_result_chars": 20_000,
            "max_iterations": 300,
            "extra_read_roots": [],
            "extra_write_roots": [],
        },
        "mcp_servers": [],
    }
    assert runtimes[0].closed is True
    assert runtimes[1].initialized is True
    assert runtimes[1].initialize_calls == 1

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        async with service.lease():
            with pytest.raises(RuntimeBusyError):
                await service.update_config({"provider": {"model": "busy"}})

    assert "[config] loaded | source=file | duration=" in caplog.text
    assert "[config] update completed | duration=" in caplog.text
    assert "[config] update rejected | reason=active_run" in caplog.text
    assert "secret" not in caplog.text

    await service.shutdown()
    assert runtimes[-1].closed is True


@pytest.mark.asyncio
async def test_runtime_service_masks_and_preserves_mcp_header_secrets(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig.from_mapping(
        {
            "provider": {"model": "test-model"},
            "mcp_servers": [
                {
                    "name": "private-server",
                    "url": "https://mcp.example.test",
                    "headers": {
                        "Authorization": "Bearer secret-token",
                        "X-Tenant": "secret-tenant",
                    },
                }
            ],
        }
    ).to_json_file(config_path)
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(config_path, runtime_factory=factory)
    await service.startup()

    public = service.public_config()
    assert public["mcp_servers"] == [
        {
            "name": "private-server",
            "url": "https://mcp.example.test",
            "headers": {
                "Authorization": "",
                "X-Tenant": "",
            },
        }
    ]

    await service.update_config(
        {
            "mcp_servers": [
                {
                    "name": "renamed-server",
                    "url": "https://mcp.example.test/v2",
                    "headers": {
                        "Authorization": "",
                        "X-Tenant": "",
                        "X-New": "new-secret",
                    },
                }
            ]
        }
    )

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    saved_server = saved["mcp_servers"][0]
    assert saved_server["name"] == "renamed-server"
    assert saved_server["url"] == "https://mcp.example.test/v2"
    assert saved_server["headers"] == {
        "Authorization": "Bearer secret-token",
        "X-Tenant": "secret-tenant",
        "X-New": "new-secret",
    }
    assert service.public_config()["mcp_servers"][0]["headers"] == {
        "Authorization": "",
        "X-Tenant": "",
        "X-New": "",
    }

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_tests_mcp_in_an_isolated_manager_and_restores_secrets(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig.from_mapping(
        {
            "mcp_servers": [
                {
                    "name": "private-server",
                    "url": "https://old.example.test/mcp",
                    "headers": {
                        "Authorization": "Bearer saved-secret",
                    },
                }
            ],
        }
    ).to_json_file(config_path)
    runtimes: list[FakeRuntime] = []
    managers: list[Any] = []

    def runtime_factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    class IsolatedManager:
        def __init__(self, *, mcp_servers: list[Any]) -> None:
            self.servers = mcp_servers
            self.closed = False
            managers.append(self)

        async def connect_mcp_server(self, server_name: str) -> list[str]:
            assert server_name == "renamed-server"
            return ["mcp_renamed-server_search"]

        async def close(self) -> None:
            self.closed = True

    service = RuntimeService(
        config_path,
        runtime_factory=runtime_factory,
        tool_manager_factory=IsolatedManager,  # type: ignore[arg-type]
    )
    await service.startup()

    registered = await service.test_mcp_server(
        {
            "name": "renamed-server",
            "url": "https://new.example.test/mcp",
            "headers": {"Authorization": ""},
        },
        original_name="private-server",
    )

    assert registered == ["mcp_renamed-server_search"]
    assert len(managers) == 1
    assert managers[0].servers[0].headers == {
        "Authorization": "Bearer saved-secret"
    }
    assert managers[0].servers[0].url == "https://new.example.test/mcp"
    assert managers[0].servers[0].tool_timeout is None
    assert managers[0].servers[0].enabled_tools == ["*"]
    assert managers[0].closed is True
    assert service.config.mcp_servers[0].name == "private-server"

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_reloads_one_or_all_mcp_servers(tmp_path) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "config.json", runtime_factory=factory)
    await service.startup()
    calls: list[str] = []

    async def reload_one(server_name: str) -> list[str]:
        calls.append(server_name)
        return [f"mcp_{server_name}_search"]

    async def reload_all() -> list[str]:
        calls.append("*")
        return ["mcp_docs_search", "mcp_github_search"]

    runtimes[0].tools = SimpleNamespace(
        reload_mcp_server=reload_one,
        reload_mcp=reload_all,
    )

    assert await service.reload_mcp_servers("docs") == ["mcp_docs_search"]
    assert await service.reload_mcp_servers() == [
        "mcp_docs_search",
        "mcp_github_search",
    ]
    assert calls == ["docs", "*"]

    async with service.lease():
        with pytest.raises(RuntimeBusyError):
            await service.reload_mcp_servers("docs")

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_exposes_settings_choices(tmp_path) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "config.json", runtime_factory=factory)
    await service.startup()
    runtime = runtimes[0]
    runtime.skills = SimpleNamespace(
        list_skills=lambda: SimpleNamespace(
            skills=[
                SimpleNamespace(
                    name="review",
                    description="Review project changes",
                )
            ],
            errors=[
                SimpleNamespace(
                    path=tmp_path / "broken" / "SKILL.md",
                    message="invalid frontmatter",
                )
            ],
        )
    )
    runtime.tools = SimpleNamespace(
        list_tools=lambda: [
            SimpleNamespace(
                name="read_file",
                description="Read a file",
                source="local",
                parallel_safe=True,
            )
        ],
        list_mcp_server_statuses=lambda: [
            SimpleNamespace(
                name="github",
                connected=True,
                registered_tools=["mcp_github_search"],
            )
        ],
    )

    assert service.settings_options() == {
        "skills": [
            {
                "name": "review",
                "description": "Review project changes",
            }
        ],
        "skill_errors": [
            {
                "path": str(tmp_path / "broken" / "SKILL.md"),
                "message": "invalid frontmatter",
            }
        ],
        "tools": [
            {
                "name": "read_file",
                "description": "Read a file",
                "source": "local",
                "parallel_safe": True,
            }
        ],
        "mcp_statuses": [
            {
                "name": "github",
                "connected": True,
                "registered_tools": ["mcp_github_search"],
            }
        ],
    }

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_manages_skills_only_while_idle(tmp_path) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "config.json", runtime_factory=factory)
    await service.startup()
    runtime = runtimes[0]
    runtime.skills = SkillsManager(tmp_path / "skills")
    source = tmp_path / "review"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review changes.\n---\n",
        encoding="utf-8",
    )

    installed = await service.install_skills([source])
    refreshed = await service.reload_skills()

    assert [skill.name for skill in installed.skills] == ["review"]
    assert [skill.name for skill in refreshed.skills] == ["review"]

    async with service.lease():
        with pytest.raises(RuntimeBusyError):
            await service.remove_skill("review")

    removed = await service.remove_skill("review")
    assert removed.skills == []

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_startup_closes_failed_runtime(tmp_path) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(
            config,
            initialize_error=RuntimeError("MCP unavailable"),
        )
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(
        tmp_path / "missing.json",
        runtime_factory=factory,
    )

    with pytest.raises(RuntimeError, match="MCP unavailable"):
        await service.startup()

    assert service.ready is False
    assert runtimes[0].initialize_calls == 1
    assert runtimes[0].closed is True


@pytest.mark.asyncio
async def test_runtime_service_keeps_current_when_replacement_init_fails(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(provider=ProviderConfig(model="old-model")).to_json_file(
        config_path
    )
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(
            config,
            initialize_error=(RuntimeError("MCP unavailable") if runtimes else None),
        )
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(config_path, runtime_factory=factory)
    await service.startup()

    with pytest.raises(RuntimeError, match="MCP unavailable"):
        await service.update_config({"provider": {"model": "new-model"}})

    assert service.config.provider.model == "old-model"
    assert (
        json.loads(config_path.read_text(encoding="utf-8"))["provider"]["model"]
        == "old-model"
    )
    assert runtimes[0].closed is False
    assert runtimes[1].initialize_calls == 1
    assert runtimes[1].closed is True

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_lists_models_with_new_url_and_key_without_saving(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(
            model="saved-model",
            api_key="saved-secret",
            base_url="https://saved.example/v1",
        )
    ).to_json_file(config_path)
    models = FakeModels(
        SimpleNamespace(
            data=[
                SimpleNamespace(id=" model-a "),
                SimpleNamespace(id="model-b"),
                SimpleNamespace(id="model-a"),
                SimpleNamespace(id="  "),
                SimpleNamespace(id=None),
            ]
        )
    )
    client_factory = FakeOpenAIClientFactory(models)
    service = RuntimeService(
        config_path,
        runtime_factory=FakeRuntime,
        openai_client_factory=client_factory,  # type: ignore[arg-type]
    )
    await service.startup()

    models = await service.list_models(
        api_key=" temporary-secret ",
        base_url=" https://DRAFT.example/v1/ ",
    )

    assert models == ["model-a", "model-b"]
    assert client_factory.calls == [
        {
            "api_key": "temporary-secret",
            "base_url": "https://draft.example/v1",
        }
    ]
    assert client_factory.clients[0].closed is True
    assert service.config.provider.api_key == "saved-secret"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["provider"]["api_key"] == "saved-secret"
    assert saved["provider"]["base_url"] == "https://saved.example/v1"

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_reuses_saved_key_for_the_same_url(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(
            api_key="saved-secret",
            base_url="https://saved.example/v1/",
        )
    ).to_json_file(config_path)
    client_factory = FakeOpenAIClientFactory(
        FakeModels(SimpleNamespace(data=[SimpleNamespace(id="saved-model")]))
    )
    service = RuntimeService(
        config_path,
        runtime_factory=FakeRuntime,
        openai_client_factory=client_factory,  # type: ignore[arg-type]
    )
    await service.startup()

    models = await service.list_models(base_url="https://SAVED.example/v1")

    assert models == ["saved-model"]
    assert client_factory.calls == [
        {
            "api_key": "saved-secret",
            "base_url": "https://saved.example/v1",
        }
    ]
    assert client_factory.clients[0].closed is True
    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_rejects_new_url_without_a_new_key(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(
            api_key="saved-secret",
            base_url="https://saved.example/v1",
        )
    ).to_json_file(config_path)
    client_factory = FakeOpenAIClientFactory(FakeModels())
    service = RuntimeService(
        config_path,
        runtime_factory=FakeRuntime,
        openai_client_factory=client_factory,  # type: ignore[arg-type]
    )
    await service.startup()

    with pytest.raises(ValueError, match="different Base URL"):
        await service.list_models(base_url="https://new.example/v1")

    assert client_factory.calls == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_wraps_model_provider_failures(tmp_path) -> None:
    from bumblehive_server.runtime_service import ModelListError

    client_factory = FakeOpenAIClientFactory(
        FakeModels(error=RuntimeError("provider unavailable"))
    )
    service = RuntimeService(
        tmp_path / "missing.json",
        runtime_factory=FakeRuntime,
        openai_client_factory=client_factory,  # type: ignore[arg-type]
    )
    await service.startup()

    with pytest.raises(ModelListError, match="third-party model query failed"):
        await service.list_models(
            base_url="https://new.example/v1",
            api_key="temporary-secret",
        )

    assert client_factory.clients[0].closed is True
    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_logs_config_load_failure(
    tmp_path,
    caplog,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")
    service = RuntimeService(config_path)

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with pytest.raises(json.JSONDecodeError):
            await service.startup()

    failure_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("[config] load failed")
    ]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is not None


@pytest.mark.asyncio
async def test_runtime_service_registers_subagent_on_startup_and_replacement(
    tmp_path,
) -> None:
    reader = RecordingSessionReader()
    runtimes: list[SubagentFakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = SubagentFakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(
        tmp_path / "config.json",
        session_reader=reader,  # type: ignore[arg-type]
        runtime_factory=factory,
    )

    await service.startup()
    await service.update_config({"provider": {"model": "replacement"}})

    assert len(runtimes) == 2
    assert all(runtime.tools.get_tool("sub_agent") is not None for runtime in runtimes)
    tool = runtimes[0].tools.get_tool("sub_agent")
    assert tool is not None
    assert tool.parameters["required"] == ["title", "task"]
    assert tool.parameters["properties"]["title"]["maxLength"] == 80
    assert "independent read-only sub-agent" in tool.description
    await service.shutdown()


@pytest.mark.asyncio
async def test_subagent_tool_runs_a_read_only_child_session(tmp_path) -> None:
    reader = RecordingSessionReader()
    observer = RecordingSubagentObserver()
    runtime: SubagentFakeRuntime | None = None

    def factory(config: BumblehiveConfig) -> Any:
        nonlocal runtime
        runtime = SubagentFakeRuntime(config)
        return runtime

    service = RuntimeService(
        tmp_path / "config.json",
        session_reader=reader,  # type: ignore[arg-type]
        runtime_factory=factory,
    )
    await service.startup()
    assert runtime is not None

    workspace = tmp_path / "workspace"
    with observe_subagents(observer):
        tool_task = _start_subagent_tool(
            runtime,
            workspace=workspace,
            title="Inspect the project",
            task="  Inspect the project  ",
        )
    await runtime.run_started.wait()

    assert reader.created_workspaces == [workspace.resolve()]
    assert reader.created_titles == ["Inspect the project"]
    assert reader.created_parent_session_ids == ["parent-session"]
    assert observer.created == [
        {
            "session_id": "child-session",
            "workspace": str(workspace.resolve()),
            "title": "Inspect the project",
            "content": "Inspect the project",
        }
    ]
    assert [event.session_id for event in observer.events] == ["child-session"]
    assert runtime.run_calls == [
        {
            "message": "Inspect the project",
            "session_id": "child-session",
            "config": {
                "runtime": {"workspace": str(workspace.resolve())},
                "agent": {
                    "tool_names": (
                        "read_file",
                        "list_dir",
                        "find_files",
                        "grep",
                    )
                },
            },
        }
    ]

    runtime.run_release.set()
    assert await tool_task == "Child answer"
    assert [item["session_id"] for item in observer.results] == [
        "child-session"
    ]
    await service.shutdown()


@pytest.mark.asyncio
async def test_subagent_tool_runs_multiple_calls_in_parallel(tmp_path) -> None:
    reader = SequentialSessionReader()
    observer = RecordingSubagentObserver()
    runtime: SubagentFakeRuntime | None = None

    def factory(config: BumblehiveConfig) -> Any:
        nonlocal runtime
        runtime = SubagentFakeRuntime(config)
        return runtime

    service = RuntimeService(
        tmp_path / "config.json",
        session_reader=reader,  # type: ignore[arg-type]
        runtime_factory=factory,
    )
    await service.startup()
    assert runtime is not None
    runtime.expected_run_count = 2

    session_token = bind_tool_session("parent-session")
    try:
        with observe_subagents(observer):
            calls_task = asyncio.create_task(
                runtime.tools.execute_many(
                    [
                        ToolCall(
                            id="call-1",
                            name="sub_agent",
                            arguments={
                                "title": "Inspect A",
                                "task": "Inspect task A",
                            },
                        ),
                        ToolCall(
                            id="call-2",
                            name="sub_agent",
                            arguments={
                                "title": "Inspect B",
                                "task": "Inspect task B",
                            },
                        ),
                    ],
                    tool_names=["sub_agent"],
                    workspace=tmp_path / "workspace",
                )
            )
    finally:
        reset_tool_session(session_token)

    await asyncio.wait_for(runtime.run_started.wait(), timeout=1)

    assert [call["message"] for call in runtime.run_calls] == [
        "Inspect task A",
        "Inspect task B",
    ]
    assert reader.created_titles == ["Inspect A", "Inspect B"]
    assert {
        call["session_id"] for call in runtime.run_calls
    } == {"child-session-1", "child-session-2"}
    assert {
        event.session_id for event in observer.events
    } == {"child-session-1", "child-session-2"}

    runtime.run_release.set()
    results = await calls_task

    assert [result.content for result in results] == [
        "Child answer",
        "Child answer",
    ]
    assert {
        item["session_id"] for item in observer.results
    } == {"child-session-1", "child-session-2"}
    await service.shutdown()


@pytest.mark.asyncio
async def test_subagent_tool_cleans_running_state_on_error_and_cancellation(
    tmp_path,
) -> None:
    reader = RecordingSessionReader()
    observer = RecordingSubagentObserver()
    runtime: SubagentFakeRuntime | None = None

    def factory(config: BumblehiveConfig) -> Any:
        nonlocal runtime
        runtime = SubagentFakeRuntime(config)
        return runtime

    service = RuntimeService(
        tmp_path / "config.json",
        session_reader=reader,  # type: ignore[arg-type]
        runtime_factory=factory,
    )
    await service.startup()
    assert runtime is not None

    runtime.run_result = SimpleNamespace(
        final_content=None,
        error=AgentError(code="model_error", message="child failed"),
    )
    with observe_subagents(observer):
        failed_task = _start_subagent_tool(
            runtime,
            workspace=tmp_path / "workspace",
            title="Test failure",
            task="Fail",
        )
    await runtime.run_started.wait()
    runtime.run_release.set()

    with pytest.raises(RuntimeError, match="child failed"):
        await failed_task
    assert [item["session_id"] for item in observer.results] == [
        "child-session"
    ]

    runtime.run_started.clear()
    runtime.run_release.clear()
    runtime.run_result = SimpleNamespace(final_content="unused", error=None)
    runtime.run_exception = RuntimeError("stream failed")
    with observe_subagents(observer):
        errored_task = _start_subagent_tool(
            runtime,
            workspace=tmp_path / "workspace",
            title="Test stream error",
            task="Error",
        )
    await runtime.run_started.wait()
    runtime.run_release.set()

    with pytest.raises(RuntimeError, match="stream failed"):
        await errored_task
    assert observer.errors == [
        {
            "session_id": "child-session",
            "message": "stream failed",
        }
    ]

    runtime.run_started.clear()
    runtime.run_release.clear()
    runtime.run_exception = None
    runtime.run_result = SimpleNamespace(final_content="unused", error=None)
    with observe_subagents(observer):
        cancelled_task = _start_subagent_tool(
            runtime,
            workspace=tmp_path / "workspace",
            title="Test cancellation",
            task="Wait",
        )
    await runtime.run_started.wait()
    cancelled_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    assert observer.cancelled == ["child-session"]
    await service.shutdown()
