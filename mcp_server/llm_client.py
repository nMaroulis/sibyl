import grpc
from llm_gateway import inference_pb2 as llm_grpc
from llm_gateway import inference_pb2_grpc as llm_pb2


class LLMClient:
    def __init__(self, host: str = "localhost", port: int = 50051):
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = llm_grpc.LLMServiceStub(self.channel)

    def generate(self, prompt: str) -> str:
        request = llm_pb2.GenerateRequest(prompt=prompt)
        response = self.stub.Generate(request)
        return response.text
