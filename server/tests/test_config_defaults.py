from bumblehive_server.config_defaults import apply_config_defaults


def test_apply_config_defaults_fills_only_effective_non_empty_values() -> None:
    source = {
        "provider": {"model": "test-model"},
        "generation": {
            "max_completion_tokens": None,
            "temperature": None,
        },
        "runtime": {
            "context_window_tokens": None,
            "max_tool_result_chars": 1234,
            "max_iterations": None,
        },
        "mcp_servers": [
            {
                "name": "docs",
                "url": "https://example.test/mcp",
            }
        ],
    }

    resolved = apply_config_defaults(source)

    assert resolved["provider"]["type"] == "openai_chat_completions"
    assert resolved["generation"] == {
        "max_completion_tokens": 16_384,
        "temperature": None,
    }
    assert resolved["runtime"] == {
        "context_window_tokens": 200_000,
        "max_tool_result_chars": 1234,
        "max_iterations": 300,
    }
    assert resolved["mcp_servers"] == source["mcp_servers"]
    assert source["generation"]["max_completion_tokens"] is None


def test_apply_config_defaults_preserves_user_values() -> None:
    resolved = apply_config_defaults(
        {
            "provider": {"type": "custom"},
            "generation": {"max_completion_tokens": 4096},
            "runtime": {
                "context_window_tokens": 32_000,
                "max_tool_result_chars": 5000,
                "max_iterations": 12,
            },
        }
    )

    assert resolved["provider"]["type"] == "custom"
    assert resolved["generation"]["max_completion_tokens"] == 4096
    assert resolved["runtime"]["context_window_tokens"] == 32_000
    assert resolved["runtime"]["max_tool_result_chars"] == 5000
    assert resolved["runtime"]["max_iterations"] == 12
