import io
import sys

import pytest

from bumblehive.console import (
    ConsoleStreamRenderer,
    compact_json,
    format_tool_hint,
    tool_result_summary,
)
from bumblehive.observability import (
    FINAL_RESULT,
    MODEL_RESPONSE_FINISHED,
    MODEL_STREAM_CONTENT_DELTA,
    MODEL_STREAM_TOOL_CALL_DELTA,
    TOOL_CALL_FINISHED,
    make_event,
)


def test_console_helpers_create_compact_user_facing_summaries() -> None:
    assert compact_json({"value": "x" * 20}, max_chars=16).endswith("...")
    assert format_tool_hint("read_file", {"path": "notes.txt"}) == "read_file notes.txt"
    assert format_tool_hint("exec", {"command": "pytest -q"}) == "exec pytest -q"
    assert tool_result_summary(
        {"tool_result": {"content": '{"entries":[1,2,3]}'}},
    ) == "3 entries"


@pytest.mark.asyncio
async def test_renderer_handles_streamed_tool_generation_execution_and_answer(monkeypatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    renderer = ConsoleStreamRenderer(verbose_tools=True)
    renderer.console.width = 1_000
    renderer.start("build a file")

    events = [
        make_event(
            MODEL_STREAM_TOOL_CALL_DELTA,
            run_id="run",
            iteration=0,
            index=0,
            name="write_file",
            arguments_delta="",
        ),
        make_event(
            MODEL_STREAM_TOOL_CALL_DELTA,
            run_id="run",
            iteration=0,
            index=0,
            name="",
            arguments_delta=(
                '{"path":"site/index.html","content":"one\\ntwo\\nthree'
            ),
        ),
        make_event(MODEL_RESPONSE_FINISHED, run_id="run", iteration=0, usage={}),
        make_event(
            TOOL_CALL_FINISHED,
            run_id="run",
            iteration=0,
            ok=True,
            duration_s=0.01,
            tool_call={"name": "write_file", "arguments": {"path": "site/index.html"}},
            tool_result={"content": '{"path":"site/index.html","success":true}'},
        ),
        make_event(
            MODEL_STREAM_CONTENT_DELTA,
            run_id="run",
            iteration=1,
            delta="Created the file.",
        ),
        make_event(FINAL_RESULT, run_id="run", final_content="Created the file."),
    ]
    for event in events:
        await renderer.on_event(event)
    await renderer.finish()

    rendered = output.getvalue()
    assert "You:" in rendered
    assert "preparing write_file site/index.html" in rendered
    assert "3 lines" in rendered
    assert "write_file ok" in rendered
    assert "Created the file." in rendered
