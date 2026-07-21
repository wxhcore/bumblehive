import pytest

from bumblehive.agent.context import ContextBuilder
from bumblehive.agent.context import builder as builder_module


def test_build_assembles_one_complete_model_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(builder_module.platform, "system", lambda: "Linux")
    history = [{"role": "assistant", "content": "previous answer"}]

    messages = ContextBuilder(timezone="UTC").build(
        current_user_message="inspect the project",
        workspace=tmp_path,
        dynamic_context={
            "active_file": "src/bumblehive/runtime.py",
            "unsafe key!": "<escaped>",
        },
        history=history,
        agent_instructions="Test agent instructions.",
        available_skills="<available_skills>demo</available_skills>",
    )

    assert [message["role"] for message in messages] == [
        "system",
        "assistant",
        "user",
    ]
    system = messages[0]["content"]
    assert "<agent_instructions>" in system
    assert "Test agent instructions." in system
    assert "<family>posix</family>" in system
    assert "<available_skills>demo</available_skills>" in system
    assert f"<cwd>{tmp_path.as_posix()}</cwd>" in system
    assert "<shell>zsh</shell>" in system

    user = messages[-1]["content"]
    assert user.startswith("inspect the project")
    assert "(UTC, UTC+00:00)" in user
    assert "<active_file>src/bumblehive/runtime.py</active_file>" in user
    assert "<unsafe_key_>&lt;escaped&gt;</unsafe_key_>" in user
    assert history == [{"role": "assistant", "content": "previous answer"}]


@pytest.mark.parametrize(
    ("system", "shell_env", "expected_family", "expected_shell"),
    [
        ("Windows", {"COMSPEC": r"C:\Windows\System32\cmd.exe"}, "windows", "cmd.exe"),
        ("Linux", {"SHELL": "/bin/bash"}, "posix", "bash"),
    ],
)
def test_build_renders_platform_specific_context(
    tmp_path,
    monkeypatch,
    system,
    shell_env,
    expected_family,
    expected_shell,
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    monkeypatch.delenv("COMSPEC", raising=False)
    for key, value in shell_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(builder_module.platform, "system", lambda: system)

    content = ContextBuilder().build(
        current_user_message="hello",
        workspace=tmp_path,
        timezone="Unknown/Timezone",
    )

    assert f"<family>{expected_family}</family>" in content[0]["content"]
    assert f"<shell>{expected_shell}</shell>" in content[0]["content"]
    assert "<current_time>" in content[-1]["content"]
    assert "Unknown/Timezone" not in content[-1]["content"]


def test_call_values_override_builder_defaults(tmp_path) -> None:
    default_workspace = tmp_path / "default"
    call_workspace = tmp_path / "call"
    builder = ContextBuilder(default_workspace, timezone="UTC")

    messages = builder.build(
        current_user_message="hello",
        workspace=call_workspace,
        timezone="Asia/Shanghai",
    )

    assert f"<cwd>{call_workspace.as_posix()}</cwd>" in messages[0]["content"]
    assert "(Asia/Shanghai, UTC+08:00)" in messages[-1]["content"]
