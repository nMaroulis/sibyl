from llm_gateway.agents.wiki_structured_agent import WikiStructuredAgent
from llm_gateway.agents.wiki_reactive_agent import WikiReactiveAgent
from llm_gateway.rag.chromadb_client import ChromaDBClient
from llm_gateway.agents.agent_base import AgentBase
from llm_gateway.llm_models.llm_base import LLMBase


class AgentFactory:
    _agents = {
        'wiki_agent': WikiStructuredAgent,
        'wiki_reactive_agent': WikiReactiveAgent,
        'wiki_rag': ChromaDBClient,
    }

    @classmethod
    def get_agent(cls, agent_name: str, llm_model: LLMBase) -> AgentBase:

        agent_class = cls._agents.get(agent_name.lower())
        if not agent_class:
            raise ValueError(f"Unknown Agent name: {agent_class}")
        return agent_class(llm_model)
