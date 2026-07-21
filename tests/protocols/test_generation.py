from bumblehive.protocols.generation import (
    DEFAULT_MAX_COMPLETION_TOKENS,
    GenerationConfig,
)


def test_max_completion_tokens_resolves_default_and_explicit_values() -> None:
    assert GenerationConfig().max_completion_tokens is None
    assert (
        GenerationConfig().effective_max_completion_tokens
        == DEFAULT_MAX_COMPLETION_TOKENS
    )
    assert GenerationConfig(4096).effective_max_completion_tokens == 4096
    assert GenerationConfig(0).effective_max_completion_tokens == 1
