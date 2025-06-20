from llm_gateway.tools.rag_retriever import DocumentRetrieverTool
from llm_gateway.tools.web_search import WebSearchTool
from llm_gateway.tools.conversation import ConversationalTool
from langchain.agents import Tool, initialize_agent, AgentExecutor, AgentType, ZeroShotAgent
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import os
from dotenv import load_dotenv
import random
from llm_gateway.llm_models.llm_base import LLMBase
from llm_gateway.agents.agent_base import AgentBase
import re
from langchain.agents.output_parsers import ReActSingleInputOutputParser


class WikiReactiveAgent(AgentBase):
    """
    The Wiki Chatbot pipeline class
    An agent based on the Reactive Langchain agentic framework
    The LLM (brain of the agent) decides which tool to use
    """

    def __init__(self, llm_model: LLMBase):

        super().__init__(llm_model)

        # ========================
        # TOOLS
        # ========================
        web_search = WebSearchTool(max_results=5)
        web_search_tool = web_search.as_langchain_tool()

        load_dotenv('database/db_paths.env')
        self.vectorstore_path = os.getenv("WIKI_VECTORSTORE_PATH")
        doc_retriever = DocumentRetrieverTool(
            persist_directory=self.vectorstore_path,
            collection_name="crypto_knowledge", threshold=0.5, k=5)
        doc_retriever_tool = doc_retriever.as_langchain_tool()

        conversation_tool = ConversationalTool().as_langchain_tool()

        self.tools = [web_search_tool, doc_retriever_tool, conversation_tool]

        # ========================
        # MEMORY SETUP
        # ========================

        # Initialize memory for conversation context
        # self.memory = ConversationSummaryMemory(memory_key="chat_history")

        # ========================
        # LLM
        # ========================
        self.llm = llm_model.as_langchain_llm()

        # ========================
        # AGENT
        # ========================

        # OPTION 1 - MODELS NOT CAPABLE FOR REACT IN THE LANGCHAIN FORMAT
        self.zeroshot_agent()

        ## OPTION 2 - MODELS CAPABLE FOR REACT IN LANGCHAIN FORMAT
        # self.react_agent()

    def react_agent(self):
        """
        Initializes a ReAct-style agent using LangChain's ZERO_SHOT_REACT_DESCRIPTION agent type.

        This agent will:
        - Use the tools provided in `self.tools`
        - Operate in a zero-shot setting, where tool descriptions are used to infer usage
        - Include memory if set
        - Provide verbose output for debugging
        - Gracefully handle parsing errors during tool invocation
        """
        self.agent = initialize_agent(
            tools=self.tools,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,  # STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION
            llm=self.llm,
            memory=self.memory,
            verbose=False,
            handle_parsing_errors=True
        )


    def zeroshot_agent(self):
        """
        Initializes a customized zero-shot agent with a custom output parser to fix formatting issues.

        This agent:
        - Uses a prompt tailored for crypto-related questions and casual conversation
        - Relies on a manually constructed ZeroShotAgent with a fixed-format output parser
        - Automatically corrects malformed action inputs (e.g., tool calls with improper formatting)
        - Waits for observations before continuing the chain of thought
        """

        class FixedFormatOutputParser(ReActSingleInputOutputParser):
            """
            Custom output parser to handle and fix improperly formatted tool action outputs.
            This ensures robust parsing even when the model outputs malformed tool invocations.
            """

            def parse(self, text: str):
                """
                Attempts to parse output; fixes the format if an error occurs.
                """
                try:
                    return super().parse(text)
                except Exception:
                    fixed_text = self._fix_format(text)
                    return super().parse(fixed_text)

            def _fix_format(self, text: str) -> str:
                """
                Fixes common formatting issues in tool action outputs such as:
                - Unquoted inputs
                - Misused parentheses
                - Incorrect input structure

                Match Langchain Style:
                 - Action: Tool("...")
                 - Action: Tool(query="...")
                 - Action: Tool(some unquoted input)
                Returns:
                    str: A reformatted string that aligns with the expected action format.
                """

                pattern = r'Action:\s*(\w+)\(\s*(?:query=)?(?:"([^"]+)"|([^\)]+))\s*\)'

                def replacer(match):
                    tool_name = match.group(1)
                    quoted_input = match.group(2)
                    raw_input = match.group(3)
                    tool_input = quoted_input if quoted_input is not None else raw_input.strip()
                    return f'Action: {tool_name}\nAction Input: "{tool_input}"'

                fixed = re.sub(pattern, replacer, text)
                return fixed

        prefix = """
        You are an AI assistant that uses tools to answer technical cryptocurrency questions
        and responds directly to casual or conversational input.

        Use ONLY the tools listed below. 
        Use "DocumentRetriever" to answer technical crypto-related queries.
        Use "WebSearch" if "DocumentRetriever" has no results or doesn't contain the answer.
        Use "ConversationalResponder" ONLY for greetings or casual conversations.

        When taking an action, follow this format:

        Thought: <reasoning>
        Action: <Tool name without parentheses>
        Action Input: <the query or input to give to the tool>

        Then, wait for the Observation. Continue until you have enough information.

        Finally, respond with:

        Final Answer: <your answer to the user>
        """

        suffix = """
        Begin!

        Question: {input}
        {agent_scratchpad}
        """


        prompt = ZeroShotAgent.create_prompt(
            self.tools,
            prefix="You are a helpful agent.",
            suffix="{input}\n\n{agent_scratchpad}",
            input_variables=["input", "agent_scratchpad"]
        )

        # Construct the agent manually
        llm_chain = LLMChain(llm=self.llm, prompt=prompt)
        agent = ZeroShotAgent(
            llm_chain=llm_chain,
            tools=self.tools,
            output_parser=FixedFormatOutputParser(),
            stop=["\nObservation:"],
        )

        # Now this uses your custom output parser
        self.agent = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            memory=None, # Stateless Run
        )


    def set_llm(self):
        pass


    def classify_query(self, query: str) -> str:
        """
        Classifies the user query as either 'Conversational' or 'Technical'.
        Uses LLM to classify the query.
        """
        template = """
        You are a highly capable AI assistant. Your job is to classify whether a user query is casual (conversational) or technical (crypto-related).
        If the query is conversational (e.g., greetings like 'Hi', 'How are you?'), simply return 'Conversational'.
        If the query is technical (e.g., crypto-related questions), return 'Technical'.

        User Query: {query}
        """

        # Format the prompt for classification
        prompt = PromptTemplate(input_variables=["query"], template=template)
        formatted_prompt = prompt.format(query=query)

        # Get the response from the LLM
        response = self.llm(formatted_prompt)

        # Take only the last line (handles the model echoing the prompt)
        response = response.strip()
        classification = response.strip().splitlines()[-1]

        # Return the classification
        if "Conversational" in classification:
            return "Conversational"
        else:
            return "Technical"


    def manual_wiki_pipeline(self, query: str) -> str:
        """
        Fallback function where the Agent logic is being run manually.

        Function to handle user queries. Classifies the query and either:
        - Returns a casual response if conversational
        - Retrieves relevant documents or performs web search if technical.
        """

        # Classify the query as either 'Conversational' or 'Technical'
        classification = self.classify_query(query)
        print("<<Wiki Agent>> - Classification", classification)
        if classification == "Conversational":
            # If conversational, just respond casually and keep memory updated
            self.memory.save_context({"input": query}, {"output": "Hi! How can I help you today?"})
            greetings = [
                "Hi! How can I help you today?",
                "Hi! How can I help you today?",
                "Hey there! Ready to explore the crypto world?",
                "Welcome! Curious about crypto? Ask me anything.",
                "Hello! Let's decode the world of crypto together.",
                "Hey! Looking for some insights into Web3 or crypto?"
            ]
            random_greeting = random.choice(greetings)
            return f"Answer: {random_greeting}"

        # If technical, search the database for relevant documents
        doc_retriever = DocumentRetrieverTool(persist_directory=self.vectorstore_path, collection_name="crypto_knowledge", threshold=0.5, k=5)
        documents = doc_retriever.retrieve(query)
        print("<<Wiki Agent>> - Documents Retrieved", len(documents))
        # IF RAG
        if len(documents) > 0:
            context = "\n".join(documents)
            prompt = f"""
                You are a knowledgeable AI assistant specialized in cryptocurrency, blockchain, and crypto technology. 
                Your goal is to provide accurate, clear, and concise answers based on the provided context. 
                If the context does not contain enough relevant information, acknowledge the limitation rather than making up an answer.

                ### User Query:
                {query}

                ### Context (Relevant Information Extracted from Documents):
                {context}

                ### Instructions:
                - Answer the user’s query **only using the provided context**.  
                - Keep your response factual, direct, and professional.  
                - If necessary, reference key concepts from blockchain, DeFi, NFTs, or cryptocurrencies to clarify your answer.  
                - Use bullet points for structured explanations when helpful.  
                ### Response:"""

            # Get the response from the LLM
            response = self.llm(prompt)
            return response
        # WEB SEARCH
        else:
            # If no documents are found in the DB, perform a web search using the WebSearch tool
            web_search = WebSearchTool(max_results=3)
            web_results = web_search.search(query)
            print("WEB RESULTS -----", web_results)
            prompt = f"""
                You are a knowledgeable AI assistant specialized in cryptocurrency, blockchain, and crypto technology. 
                Your goal is to provide accurate, clear, and concise answers based on the provided context. 
                If the context does not contain enough relevant information, acknowledge the limitation rather than making up an answer.

                ### User Query:
                {query}

                ### Context (Relevant Information Extracted from the Web):
                {web_results}

                ### Instructions:
                - Answer the user’s query **only using the provided context**.  
                - If the context does not contain enough information, state:  
                  *"The provided information does not contain enough details to answer your question. Would you like me to suggest general insights based on my knowledge?"*  
                - Keep your response factual, direct, and professional.  
                ### Response:"""

            # Get the response from the LLM
            response = self.llm(prompt)
            return response


    def run(self, query: str) -> str:

        # ========================
        # AGENT EXECUTION LOGIC
        # ========================

        # Option 1 - Manual Pipeline
        # res = self.manual_wiki_pipeline(query)

        # Option 2 - AI Agent

        res = self.agent.invoke(input=query)
        return res

        # CUSTOM THOUGH PROMPTING
        # try:
        #     response = self.agent.run(query)
        #     # Ensure the response ends with a Final Answer
        #     if "Final Answer:" not in response:
        #         thought = "I should provide a clear final answer."
        #         response = f"{response}\nThought: {thought}\nFinal Answer: {response}"
        #     return response
        # except Exception as e:
        #     print(f"Agent execution failed: {e}")
        #     return "Sorryyyyyyyyyyyyy" # self.manual_wiki_pipeline(query)



