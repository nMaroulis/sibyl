"""Request-scoped model selection for persistent native ProtoLink agents."""

import asyncio
from contextvars import ContextVar
from typing import ClassVar

from protolink.llms.base import LLM

from sibyl.agents.common import Turn, current_turn

current_agent: ContextVar[str] = ContextVar("sibyl_model_agent", default="")


class WorkspaceLLM(LLM):
    """Keep agents registered while provider settings change between turns.

    ProtoLink owns the inference/action loop, history, discovery and delegation.
    This adapter only selects a private provider instance per agent/turn and
    moves blocking provider I/O off the API loop. It uses the SDK's portable
    JSON action format, which also supports native ``agent_call`` actions.
    """

    provider: ClassVar[str] = "workspace"
    model_type: ClassVar[str] = "api"

    def __init__(self, module: str, make_model, configuration):
        super().__init__(model="workspace", model_params={})
        self.module, self.make_model, self.configuration = module, make_model, configuration

    async def infer(self, **kwargs):
        """Support plain AgentClient tasks as well as browser requests and native child tasks."""
        if current_turn.get() is not None:
            return await super().infer(**kwargs)
        context = kwargs.get("run_context")
        turn = Turn(
            self.configuration(), module=self.module, session_id=getattr(context, "session_id", "") or ""
        )
        token = current_turn.set(turn)
        try:
            return await super().infer(**kwargs)
        finally:
            current_turn.reset(token)

    def call(self, history):
        """Generate with this agent's adapter from the turn's frozen provider/key snapshot."""
        turn = current_turn.get()
        if turn is None:
            raise RuntimeError("No model is configured for this request.")
        token = current_agent.set(self.module)
        try:
            if self.module not in turn.models:
                turn.models[self.module] = self.make_model(turn.configuration)
            return turn.models[self.module].call(history)
        finally:
            current_agent.reset(token)

    async def call_action(self, history, **kwargs):
        """Use ProtoLink's action parser/validator without blocking its event loop."""
        return await asyncio.to_thread(super().call_action, history.copy(), **kwargs)

    async def call_stream(self, history):
        """Support ProtoLink's delegated task stream with complete action responses."""
        yield await asyncio.to_thread(self.call, history.copy())

    def validate_connection(self) -> bool:
        """Report configuration presence only; never probe a paid provider during startup."""
        turn = current_turn.get()
        return bool(turn and self.module in turn.models)
