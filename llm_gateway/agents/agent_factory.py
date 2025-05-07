from llm_gateway.agents.WikiAgent import WikiAgent
from llm_gateway.rag.chromadb_client import ChromaDBClient
from llm_gateway.agents.agent_base import AgentBase
from llm_gateway.llm_models.llm_base import LLMBase

class AgentFactory:
    _agents = {
        'wiki_agent': WikiAgent,
        'wiki_rag': ChromaDBClient,
    }

    @classmethod
    def get_agent(cls, agent_name: str, llm_model: LLMBase) -> AgentBase:

        agent_class = cls._agents.get(agent_name.lower())
        if not agent_class:
            raise ValueError(f"Unknown Agent name: {agent_class}")
        return agent_class(llm_model)
