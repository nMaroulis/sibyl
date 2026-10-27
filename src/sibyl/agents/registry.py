"""Wire the module declarations to existing services and preserve the HTTP response contract."""

import asyncio
import json
from uuid import uuid4

from protolink import RunBudget, Task, create_llm, current_request_context, request_context

from sibyl.agents import (
    accountant,
    analyst,
    broker,
    chronos,
    explorer,
    oracle,
    reporter,
    stocks,
    technician,
    wiki,
)
from sibyl.agents.common import Services, freeze
from sibyl.agents.model_selection import readiness
from sibyl.agents.network import AgentNetwork
from sibyl.agents.snapshots import snapshot_answer, tool_arguments
from sibyl.models import AgentRequest
from sibyl.services.llm_settings import ModelSettings

MODULES = {
    "oracle": oracle,
    "accountant": accountant,
    "analyst": analyst,
    "broker": broker,
    "chronos": chronos,
    "reporter": reporter,
    "technician": technician,
    "wiki": wiki,
    "explorer": explorer,
    "stocks": stocks,
}
ROLES = {key: (module.NAME, module.TAGLINE, module.DESCRIPTION) for key, module in MODULES.items()}


class AgentRegistry:
    """Compose each agent once; model requests use its tools on demand, never preload observations."""

    def __init__(
        self,
        settings,
        store,
        market,
        portfolio,
        strategies,
        research,
        account_sync=None,
        performance=None,
        funding=None,
        transfers=None,
    ):
        self.settings, self.store = settings, store
        self.models = ModelSettings(settings, store)
        self.services = Services(
            settings,
            store,
            market,
            portfolio,
            strategies,
            research,
            account_sync,
            performance,
            funding,
            transfers,
        )
        self._semaphore = asyncio.Semaphore(2)
        self.network = AgentNetwork(self, MODULES)
        self.agents = {key: self.network.agents[key] for key in MODULES}

    def make_model(self, configuration: dict):
        """Construct a ProtoLink provider from this turn's frozen settings, off the API loop."""
        reason = readiness(configuration)
        if reason:
            raise ValueError(reason)
        provider, kwargs = self.models.constructor(configuration)
        return create_llm(provider, **kwargs)

    def model_for(self, module: str):
        """Native lazy factory: choose this agent's model from the accepted team snapshot.

        Plain AgentClient requests have no private caller context across the transport
        boundary, so they resolve current settings in this receiving application.
        """
        private = current_request_context()
        configuration = private.get("models") or freeze(self.models.for_turn(module))
        with request_context({**private, "agent_id": module}):
            return self.make_model(configuration["_agents"][module])

    def catalog(self) -> list[dict]:
        """Expose real native tool names and runtime URLs without provider credentials."""
        selection = self.models.for_turn("sibyl")
        return [
            {
                "id": key,
                "name": module.NAME,
                "tagline": module.TAGLINE,
                "description": module.DESCRIPTION,
                "engine": "ProtoLink",
                "tool": next(iter(self.agents[key].tools)),
                "tools": list(self.agents[key].tools),
                "url": self.agents[key].card.url,
                "mode": "tools" if selection["_agents"][key]["provider"] == "none" else "llm",
                "provider": selection["_agents"][key]["provider"],
                "model": selection["_agents"][key]["model"],
                "model_selection": selection["_selections"][key],
                "model_ready": not readiness(selection["_agents"][key]),
                "model_reason": readiness(selection["_agents"][key]),
                "registered": self.network.ready,
                "transport": "runtime",
            }
            for key, module in MODULES.items()
        ]

    async def ask(self, request: AgentRequest) -> dict:
        """Run a module dialog through its registered specialist's native group handle."""
        return await self.network.ask_module(request)

    async def _answer(self, request: AgentRequest, configuration: dict) -> dict:
        """Persist a UI reply projected from the native result and completed evidence."""
        session_id = request.session_id or uuid4().hex
        context = request.context.model_dump(exclude_none=True, exclude_unset=True)
        primary_tool = next(iter(self.agents[request.module].tools))
        with request_context({"models": configuration, "page": freeze(context)}, inherit=("models", "page")):
            if configuration["provider"] == "none":
                task = Task.create_tool_call(primary_tool, tool_arguments(request), session_id=session_id)
                mode = "tools"
            else:
                task = Task.create_infer(
                    f"Validated page selection (defaults, not evidence): {json.dumps(context)}\n"
                    f"Question: {request.message}",
                    session_id=self.network.session_key(request.module, session_id, context),
                    budget=RunBudget(max_steps=8, max_llm_calls=8, max_tool_calls=6, max_runtime_seconds=80),
                )
                mode = "llm"
            execution = await self.network.send(request.module, task)
        content = execution.output
        observations = self.network.observations(execution.tool_evidence)
        evidence = content if mode == "tools" else observations[0]["evidence"] if observations else {}
        answer = snapshot_answer(request.module, evidence) if mode == "tools" else str(content)
        result = {
            "module": request.module,
            "session_id": session_id,
            "question": request.message,
            "context": context,
            "answer": answer,
            "engine": "ProtoLink",
            "mode": mode,
            "provider": configuration["provider"],
            "model": configuration["model"],
            "model_selection": configuration.get("_selections", {}).get(request.module, "default"),
            "tool": observations[0]["tool"] if observations else primary_tool,
            "evidence": evidence,
            "observations": observations,
            "run_id": execution.report.context.run_id,
        }
        record = self.store.record("agent", result)
        return {**result, "id": record["id"], "created_at": record["created_at"]}
