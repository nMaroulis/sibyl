from fastapi import APIRouter, HTTPException
from grpc import insecure_channel
from backend.config import inference_pb2
from backend.config import inference_pb2_grpc
from backend.src.wiki.funcs import check_exists_chroma_db, check_exists_llm_api

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/wiki",
    tags=["Wiki Chatbot"],
    responses={404: {"description": "Not found"}},
)


@router.get("/chatbot/query")
def get_llm_advice(query: str):
    try:
        # Call gRPC server
        channel = insecure_channel("localhost:50051") # TODO not static str for ip:port
        stub = inference_pb2_grpc.InferenceServiceStub(channel)
        request = inference_pb2.PredictRequest(model_name="wiki_rag", input_text=query)
        response = stub.Predict(request)

        return {"status": "success", "data": response.output_text}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="LLM API failed")


@router.get("/rag/status")
def get_rag_status():
    try:
        return {"embeddings_db": check_exists_chroma_db(), "llm_api": check_exists_llm_api("hugging_face")}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="Rag status failed!")
