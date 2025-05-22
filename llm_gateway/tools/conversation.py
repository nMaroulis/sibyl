from langchain.agents import Tool
from llm_gateway.tools.base_tool import BaseTool
import random



class ConversationalTool(BaseTool):

    def __init__(self):
        pass

    def conversational_response(self, query: str = None) -> str:
        greetings = [
            "Hi! How can I help you today?",
            "Hi! How can I help you today?",
            "Hi there! How can I assist you today?"
            "Hey there! Ready to explore the crypto world?",
            "Welcome! Curious about crypto? Ask me anything.",
            "Hello! Let's decode the world of crypto together.",
            "Hey! Looking for some insights into Web3 or crypto?"
        ]
        random_greeting = random.choice(greetings)
        return f"Answer: {random_greeting}"


    def as_langchain_tool(self) -> Tool:
        return Tool(
            name="ConversationalResponder",
            func=self.conversational_response,
            description="Use this tool when the user is making small talk, greetings, or asking non-technical, casual questions."
        )

