from mcp.server.fastmcp import FastMCP
from mcp_server.agent_pipeline import AgentPipeline


pipeline = AgentPipeline(brave_api_key="...")

mcp = FastMCP("CryptoAssistantMCP")

@mcp.agent()
async def crypto_agent(context, message):
    query = message.content
    user_id = context.session_id or "anonymous"

    response = await pipeline.handle_query(user_id=user_id, query=query)

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.app, host="0.0.0.0", port=8081, reload=True)
