from pathlib import Path

import pytest

from bumblehive.config.schema import (
    AgentConfig,
    BumblehiveConfig,
    ProviderConfig,
    RuntimeArguments,
    RuntimeConfig,
)
from bumblehive.protocols import GenerationConfig, MCPServerConfig


def test_exec_path_restriction_is_opt_in() -> None:
    assert RuntimeConfig().restrict_exec_paths is False
    assert (
        BumblehiveConfig.from_dict({"provider": {"model": "demo-model"}})
        .runtime.restrict_exec_paths
        is False
    )


def test_config_round_trips_all_public_sections(tmp_path) -> None:
    config = BumblehiveConfig(
        provider=ProviderConfig(
            model="demo-model",
            api_key="secret",
            base_url="https://example.test/v1",
        ),
        generation=GenerationConfig(
            max_completion_tokens=123,
            temperature=0.4,
            reasoning_effort="medium",
            extra_body={"thinking": True},
        ),
        agent=AgentConfig(
            instructions="Be concise.",
            dynamic_context={"project": "bumblehive"},
            skill_names=("audit",),
            tool_names=("read_file",),
        ),
        runtime=RuntimeConfig(
            workspace=str(tmp_path),
            timezone="UTC",
            context_window_tokens=4096,
            max_tool_result_chars=2048,
            max_iterations=12,
            extra_read_roots=(str(tmp_path / "read"),),
            extra_write_roots=(str(tmp_path / "write"),),
            restrict_exec_paths=True,
        ),
        mcp_servers=(
            MCPServerConfig(
                name="docs",
                url="https://example.test/mcp",
                headers={"Authorization": "Bearer token"},
                tool_timeout=45,
                enabled_tools=["search"],
            ),
        ),
        skills_dir=str(tmp_path / "skills"),
    )

    data = config.to_dict()

    assert BumblehiveConfig.from_dict(data) == config
    assert data["runtime"]["extra_read_roots"] == [str(tmp_path / "read")]
    assert data["runtime"]["restrict_exec_paths"] is True
    assert data["mcp_servers"][0]["enabled_tools"] == ["search"]
    assert data["skills_dir"] == str(tmp_path / "skills")


def test_runtime_arguments_build_the_same_structured_config(tmp_path) -> None:
    config = RuntimeArguments(
        model="demo-model",
        api_key="secret",
        workspace=Path(tmp_path),
        timezone="UTC",
        extra_read_roots=[tmp_path / "read"],
        extra_write_roots=[tmp_path / "write"],
        restrict_exec_paths=True,
        agent_instructions="Be concise.",
        skill_names=["audit"],
        tool_names=["read_file"],
        skills_dir=tmp_path / "skills",
    ).to_config()

    assert config.provider.model == "demo-model"
    assert config.generation.max_completion_tokens is None
    assert config.runtime.workspace == str(tmp_path)
    assert config.runtime.extra_read_roots == (str(tmp_path / "read"),)
    assert config.runtime.extra_write_roots == (str(tmp_path / "write"),)
    assert config.runtime.restrict_exec_paths is True
    assert config.agent.instructions == "Be concise."
    assert config.agent.skill_names == ("audit",)
    assert config.agent.tool_names == ("read_file",)
    assert config.skills_dir == str(tmp_path / "skills")


@pytest.mark.parametrize("model", [None, "", "   "])
def test_provider_config_preserves_an_unset_model(model) -> None:
    assert ProviderConfig(model=model).model == model


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"provider": []}, "provider config must be a mapping"),
        (
            {
                "provider": {"model": "test-model"},
                "agent": {"dynamic_context": []},
            },
            "dynamic_context must be a mapping",
        ),
        (
            {
                "provider": {"model": "test-model"},
                "runtime": {"extra_read_roots": "/tmp"},
            },
            "must be a sequence",
        ),
        (
            {
                "provider": {"model": "test-model"},
                "runtime": {"restrict_exec_paths": "false"},
            },
            "must be a bool",
        ),
        (
            {
                "provider": {"model": "test-model"},
                "mcp_servers": "docs",
            },
            "mcp_servers must be a sequence",
        ),
        (
            {
                "provider": {"model": "test-model"},
                "mcp_servers": [{}],
            },
            "name is required",
        ),
        (
            {
                "provider": {"model": "test-model"},
                "mcp_servers": [{"name": "docs"}],
            },
            "url is required",
        ),
    ],
)
def test_config_rejects_invalid_section_shapes(data, message) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        BumblehiveConfig.from_mapping(data)
