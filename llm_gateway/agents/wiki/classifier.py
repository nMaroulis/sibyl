def classify_query(query, llm):
    prompt = f"""
    Classify the query as one of:
    - CONVERSATION
    - INFO
    - UNKNOWN
    
    Query: {query}
    Answer:"""
    return llm(prompt).strip().upper()
