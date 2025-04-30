from langchain.agents import initialize_agent, AgentType
from langchain.chains import RetrievalQA
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool

from llm_gateway.llm_models.api.hf_api_llm import HuggingFaceAPILLM
from llm_gateway.llm_models.llama_cpp.llama_cpp_llm import LlamaCppLocalLLM
from vectorstore.chroma import get_vectorstore

from llm_gateway.tools.local_search import search_tool
from llm_gateway.tools.web_search import web_search_tool
from llm_gateway.agents.wiki.classifier import classify_query


# Shared memory across agent calls
memory = ConversationBufferMemory(memory_key="chat_history")

# RetrievalQA chain (wrapper around vector DB)
vectorstore = get_vectorstore()
retriever = vectorstore.as_retriever()
llm = HuggingFaceAPILLM().as_langchain_llm()
# llm = LlamaCppLocalLLM().as_langchain_llm()

retrieval_qa_tool = Tool(
    name="RetrievalQA",
    func=RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    ).run,
    description="Useful for answering questions using internal knowledge base."
)


def run_agent(query: str):
    llm = get_llm()
    label = classify_query(query, llm)

    if label == "CONVERSATION":
        return llm(f"You are a friendly chatbot. User: {query}\nAI:")

    tools = [retrieval_qa_tool, search_tool]

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=True
    )

    result = agent.run(query)

    # Check if retrievalQA or local search didn't help
    if any(phrase in result.lower() for phrase in ["no relevant", "don't know", "not sure"]):
        web_agent = initialize_agent(
            tools=[web_search_tool],
            llm=llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            memory=memory,
            verbose=True
        )
        result = web_agent.run(query)

    return result
