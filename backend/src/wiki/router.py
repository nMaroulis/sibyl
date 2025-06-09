from fastapi import APIRouter, HTTPException
from grpc import insecure_channel
from backend.config import inference_pb2
from backend.config import inference_pb2_grpc
from backend.src.wiki.utils import check_exists_chroma_db, check_exists_llm_api
from dotenv import load_dotenv
import os
from typing import Optional
from backend.src.wiki.schemas import VectorStoreStatusResponse, WikiAgentResponse

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/wiki",
    tags=["Wiki Chatbot"],
    responses={404: {"description": "Not found"}},
)


@router.get("/chatbot/query", response_model=WikiAgentResponse)
def get_wiki_agent_response(model_source: str, model_type: str, query: str, model_name: Optional[str] = None, agent_type: str = "wiki_agent"):
    try:
        # Call gRPC server
        load_dotenv('llm_gateway/server_config.env')
        channel = insecure_channel(f"{os.getenv("GRPC_INFERENCE_SERVER_IP")}:{os.getenv("GRPC_INFERENCE_SERVER_PORT")}")
        stub = inference_pb2_grpc.InferenceServiceStub(channel)

        kwargs = {
            "application": agent_type,
            "model_source": model_source,
            "model_type": model_type,
            "input_text": query
        }
        if model_name:
            kwargs["model_name"] = model_name

        request = inference_pb2.AgentRequest(**kwargs)
        response = stub.AgentExecute(request)

        return {"status": "success", "data": response.output_text}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="LLM API failed")



# @router.get("/chatbot/query")
# def get_llm_advice(query: str):
#     try:
#         # Call gRPC server
#         load_dotenv('llm_gateway/server_config.env')
#         channel = insecure_channel(f"{os.getenv("GRPC_INFERENCE_SERVER_IP")}:{os.getenv("GRPC_INFERENCE_SERVER_PORT")}")
#         stub = inference_pb2_grpc.InferenceServiceStub(channel)
#         request = inference_pb2.PredictRequest(model_name="wiki_rag", input_text=query)
#         response = stub.Predict(request)
#
#         return {"status": "success", "data": response.output_text}
#     except Exception as e:
#         print(e)
#         raise HTTPException(status_code=404, detail="LLM API failed")


@router.get("/rag/vectorstore/status", response_model=VectorStoreStatusResponse)
def get_vectorstore_status():
    try:
        return {"embeddings_db": check_exists_chroma_db()}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="Retrieving wiki vectorstore status failed!")
