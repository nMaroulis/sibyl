from langchain.agents import Tool
from llm_gateway.tools.base_tool import BaseTool



class ConversationalTool(BaseTool):

    def __init__(self):
        pass

    def conversational_response(self, query: str = None) -> str:
        return "Hi there! How can I assist you today?"

    def as_langchain_tool(self) -> Tool:
        return Tool(
            name="ConversationalResponder",
            func=self.conversational_response,
            description="Use this tool when the user is making small talk, greetings, or asking non-technical, casual questions."
        )

