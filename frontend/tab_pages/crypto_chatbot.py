import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.wiki_helper.client import fetch_wiki_rag_response
import time

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

st.success("**Embeddings Database** and **valid LLM API key** were successfully retrieved.", icon=":material/task_alt:")
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

    with st.chat_message("assistant"):
        bot_response = fetch_wiki_rag_response(user_input)
        # st.write(bot_response)
        response_placeholder = st.empty()
        displayed_text = ""
        for word in bot_response.split():
            displayed_text += word + " "
            response_placeholder.write(displayed_text)  # Update the text
            time.sleep(0.05)  # Add delay for effect

    st.session_state.wiki_chatbot_messages.append({"role": "assistant", "content": bot_response})
