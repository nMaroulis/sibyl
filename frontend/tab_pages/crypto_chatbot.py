import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.wiki_helper.client import fetch_wiki_rag_response, fetch_vectorstore_status
import time
from frontend.db.db_connector import fetch_llm_config


fix_page_layout('💬 Chatbot')
set_page_title("Crypto Wiki Chatbot 💬")

@st.dialog(title="Crypto Wiki RAG System", width="large")
def show_info():
    st.markdown("""
        **Step 1: Query Embedding**\n
        The user’s question is converted into a dense vector using Sentence Transformers (all-MiniLM-L6-v2).\n
        **Step 2: Hybrid Retrieval (Vector + Keyword Search)**\n
        The system retrieves candidate documents using:\n
        - Vector Search (ChromaDB)
        - BM25 (Rank-BM25 for keyword relevance)\n
        **Step 3: Reranking with Cross-Encoder**\n
        The retrieved results are re-ranked using a Cross-Encoder (ms-marco-MiniLM-L-6-v2).\n
        The highest-scoring document is selected as the best answer.\n
        **Step 4: Threshold-Based Filtering**\n
        If the relevance score < threshold (e.g., 0.5) → The system responds with:\n
        "I couldn't find relevant information in the knowledge base.". 
        This prevents hallucinations and ensures accuracy.\n
        **Step 5: LLM Completion for Final Answer**\n
        Instead of returning the document as-is, we format it into a prompt and send it to an LLM (e.g., GPT-4, Mistral, or Llama-3 via Hugging Face API).""")

with st.expander("✏️ Instructions"):
    st.write("This crypto chatbot is based on a **RAG** system which contains multiple documents related to crypto (whitepapers, technical details, articles etc.). In order to use this functionality, 1. the **Embeddings Database** (chromadb) needs to be downloaded locally in the */database/wiki_rag* directory and 2. have a **valid API key** for Hugging Face, OpenAI API or Google's gemini stored in the encrypted Database.")
    if st.button('ℹ️ Learn more'):
        show_info()

vectorstore_status = fetch_vectorstore_status()
oracle_status = fetch_llm_config()

if not vectorstore_status:
    st.warning("**Embeddings Database** was not found on your filesystem.", icon=":material/warning_alt:")
    st.button("Download Wiki RAG Database", icon=":material/download:", type="primary")
else:
    st.sidebar.badge("**Embeddings Database** is configured", icon=":material/database:", color="green")

if not oracle_status:
    st.warning("**Oracle** is not configured, so the LLM functionality of the Wiki Chatbot is not available.", icon=":material/warning_alt:")
    st.link_button("Setup Oracle in Settings", "http://localhost:8501/settings", type="primary", icon=":material/settings:")
else:
    st.sidebar.badge("**Oracle** is configured", icon=":material/local_fire_department:", color="green")


st.html("""<hr style="height:1px; color:#e3e3e3; background-color:#e3e3e3; padding:0; margin:0;">""")

if "wiki_chatbot_messages" in st.session_state:
    if st.sidebar.button("Reset Chat", icon=":material/backspace:", type="primary", use_container_width=True):
        del st.session_state["wiki_chatbot_messages"]
else:
    st.sidebar.button("Reset Chat", icon=":material/backspace:", type="primary", use_container_width=True, disabled=True)


if "wiki_chatbot_messages" not in st.session_state:
    st.session_state["wiki_chatbot_messages"] = []

# Display chat history
for message in st.session_state["wiki_chatbot_messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if user_input := st.chat_input("What would you like to know?"):
    st.session_state.wiki_chatbot_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # RESPONSE ELEMENT
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            bot_response = fetch_wiki_rag_response(model_source=oracle_status["llm_source"], model_type=oracle_status["llm_type"], model_name=oracle_status["llm_name"], query=user_input)
        response_placeholder = st.empty()
        displayed_text = ""
        for word in bot_response.split(" "):
            displayed_text += word + " "
            response_placeholder.write(displayed_text)  # Update the text
            time.sleep(0.05)  # Add delay for effect

    st.session_state.wiki_chatbot_messages.append({"role": "assistant", "content": bot_response})
