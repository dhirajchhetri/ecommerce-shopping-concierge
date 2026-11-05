"""Offline model for the Strands agent loop.

It emits the same tool-call stream a hosted model would. The tool sequence
comes from planner.plan_next, which only sees the conversation so far.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel
from typing_extensions import override

from strands.models import Model
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

from kitline.planner import force_flag, latest_user_text, parse_tool_results, plan_next


def _events(name: str, payload: dict, tool_use_id: str) -> list[StreamEvent]:
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {"toolUse": {"name": name, "toolUseId": tool_use_id}},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {"toolUse": {"input": json.dumps(payload)}},
            }
        },
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]


class StubModel(Model):
    """Deterministic stand-in used when KITLINE_MODE=offline."""

    def __init__(self, fault: str = "honest") -> None:
        self.fault = fault
        self._config: dict[str, Any] = {"model_id": "kitline-stub"}
        self._calls = 0

    @override
    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    @override
    def get_config(self) -> Any:
        return dict(self._config)

    @override
    async def structured_output(
        self,
        output_model: type[BaseModel],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        text = latest_user_text(prompt)
        call = plan_next(text, parse_tool_results(prompt), force_bad=force_flag(self.fault, text))
        if call.name != output_model.__name__:
            # Walk the tool plan until it produces the requested schema. The agent
            # loop normally does this through stream(); this method covers direct calls.
            results = parse_tool_results(prompt)
            guard = 0
            while call.name != output_model.__name__ and guard < 8:
                guard += 1
                call = plan_next(text, results, force_bad=force_flag(self.fault, text))
        try:
            yield {"output": output_model.model_validate(call.arguments)}
        except Exception as exc:
            raise ValueError(f"Stub could not build {output_model.__name__}.") from exc

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        del tool_specs, system_prompt, system_prompt_content, invocation_state
        text = latest_user_text(messages)
        call = plan_next(text, parse_tool_results(messages), force_bad=force_flag(self.fault, text))
        forced = None
        if isinstance(tool_choice, dict) and "tool" in tool_choice:
            forced = tool_choice["tool"].get("name")
        if forced and call.name != forced and forced == "BundleProposal":
            # The caller asked for the schema tool. Keep planning only when we are
            # not mid tool-gathering; otherwise honor the planner.
            pass
        self._calls += 1
        for event in _events(call.name, call.arguments, f"stub-{self._calls}"):
            yield event
