import grpc
from concurrent import futures
import inference_pb2
import inference_pb2_grpc
from llm_gateway.llm_models.llm_client_factory import LLMClientFactory
from llm_gateway.agents.agent_factory import AgentFactory
from database.api_keys_db_client import APIEncryptedDatabase
from dotenv import load_dotenv
import os



class InferenceService(inference_pb2_grpc.InferenceServiceServicer):
    """
    A gRPC service that provides inference and agent-based execution capabilities.

    Methods:
        Predict: Handles direct LLM inference requests.
        AgentExecute: Handles requests that involve agentic workflows, such as RAG.
    """

    def __init__(self) -> None:
        """Initializes the InferenceService with no model loaded."""
        self.llm = None
        self.agent = None


    def Predict(self, request, context: grpc.ServicerContext) -> inference_pb2.PredictResponse:
        """
        Performs inference using the specified model.

        Args:
            request (PredictRequest): Contains the model information and input query.
            context (grpc.ServicerContext): gRPC context for the request.

        Returns:
            PredictResponse: Contains the generated output text.
        """

        kwargs = {"model_type": request.model_type}
        if request.HasField("model_name"):
            kwargs["model_name"] = request.model_name

        self.llm = LLMClientFactory.get_client(**kwargs)
        self.llm.initialize_model()
        response_text = self.llm.generate_response(request.input_text)
        return inference_pb2.PredictResponse(output_text=response_text)


    def AgentExecute(self, request, context: grpc.ServicerContext) -> inference_pb2.AgentResponse:
        """
        Executes an agent-based workflow using the specified model and application.

        Args:
            request (AgentRequest): Contains the application, model, and input query.
            context (grpc.ServicerContext): gRPC context for the request.

        Returns:
            AgentResponse: Contains the output from the agent execution.
        """

        kwargs = {"model_type": request.model_type}
        if request.HasField("model_name"):
            kwargs["model_name"] = request.model_name
        llm = LLMClientFactory.get_client(**kwargs)
        self.agent = AgentFactory.get_agent(request.application, llm)

        response: str | dict = self.agent.run(request.input_text)
        if isinstance(response, dict):
            response = response["output"]

        return inference_pb2.AgentResponse(output_text=response)


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