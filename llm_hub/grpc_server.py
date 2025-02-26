import grpc
from concurrent import futures
import inference_pb2
import inference_pb2_grpc
from llm_hub.llm_models.llm_client_factory import LLMClientFactory
from database.api_keys_db_client import APIEncryptedDatabase


class InferenceService(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, model_name: str = "hugging_face"):
        self.model = LLMClientFactory.get_client(model_name)

    def Predict(self, request, context):
        response_text = self.model.generate_response(request.input_text)
        return inference_pb2.PredictResponse(output_text=response_text)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(InferenceService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    # Initialize encryption and API storage database
    APIEncryptedDatabase.init_cipher()
    APIEncryptedDatabase.init_db()
    print("gRPC :: Starting Server on port 50051...")
    serve()