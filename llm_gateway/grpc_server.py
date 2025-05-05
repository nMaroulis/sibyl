import grpc
from concurrent import futures
import inference_pb2
import inference_pb2_grpc
from llm_gateway.llm_models.llm_client_factory import LLMClientFactory
from database.api_keys_db_client import APIEncryptedDatabase
from dotenv import load_dotenv
import os


class InferenceService(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self):
        self.model = None # LLMClientFactory.get_client(model_name)

    def Predict(self, request, context):

        self.model = LLMClientFactory.get_client(request.model_name)
        response_text = self.model.generate_response(request.input_text)
        return inference_pb2.PredictResponse(output_text=response_text)


    def AgentExecute(self, request, context):
        pass


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(InferenceService(), server)

    load_dotenv('llm_gateway/server_config.env')
    server.add_insecure_port(f"{os.getenv("GRPC_INFERENCE_SERVER_IP")}:{os.getenv("GRPC_INFERENCE_SERVER_PORT")}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    # Initialize encryption and API storage database
    APIEncryptedDatabase.init_cipher()
    APIEncryptedDatabase.init_db()
    print("gRPC :: Starting Inference Server...")
    serve()