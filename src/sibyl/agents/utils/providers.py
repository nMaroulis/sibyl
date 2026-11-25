"""ProtoLink provider metadata and curated, editable model suggestions.

Presets are suggestions, not availability checks. Local servers must already
have the chosen model installed. See the linked provider catalogs for changes.
"""

import re
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from typing import Literal

ProviderId = Literal[
    "none",
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "grok",
    "huggingface",
    "openai-compatible",
    "ollama",
    "lmstudio",
    "vllm",
    "llama.cpp-server",
    "llama.cpp-local",
    "mock",
]


@dataclass(frozen=True)
class Provider:
    """UI choices and constructor capabilities for one ProtoLink adapter."""

    id: str
    name: str
    kind: str
    description: str
    models: tuple[str, ...] = ()
    base_url: str = ""
    key_env: tuple[str, ...] = ()
    requires_key: bool = False
    dependency: str = ""
    extra: str = ""
    docs_url: str = ""

    def public(self) -> dict:
        """Return non-secret catalog metadata without importing optional SDKs."""
        try:
            installed = not self.dependency or find_spec(self.dependency) is not None
        except ModuleNotFoundError:
            installed = False
        return {
            **asdict(self),
            "installed": installed,
            "context_windows": API_CONTEXT_WINDOWS.get(self.id, {}),
            "supports_output_limit": self.id in API_OUTPUT_PARAMETERS,
        }


PROVIDERS = {
    p.id: p
    for p in [
        Provider("none", "Tool mode", "tools", "Module tools without a language model."),
        Provider(
            "openai",
            "OpenAI",
            "api",
            "GPT models through the Responses API.",
            (
                "gpt-6.2-sol",
                "gpt-6.2-astra",
                "gpt-6.1-terra",
                "gpt-6-luna",
                "gpt-6.1-sol",
                "gpt-4.1-mini",
            ),
            key_env=("OPENAI_API_KEY",),
            requires_key=True,
            dependency="openai",
            extra="openai",
            docs_url="https://developers.openai.com/api/docs/models",
        ),
        Provider(
            "anthropic",
            "Anthropic",
            "api",
            "Claude for reasoning and conversation.",
            ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5", "claude-fable-5-2"),
            key_env=("ANTHROPIC_API_KEY",),
            requires_key=True,
            dependency="anthropic",
            extra="anthropic",
            docs_url="https://platform.claude.com/docs/en/models/overview",
        ),
        Provider(
            "gemini",
            "Google Gemini",
            "api",
            "Gemini models through Google AI.",
            (
                "gemini-4-neon",
                "gemini-4-carbon",
                "gemini-4-hydrogen",
                "gemini-4-argon",
                "gemini-3.8-flash",
            ),
            key_env=("GEMINI_API_KEY",),
            requires_key=True,
            dependency="google.genai",
            extra="gemini",
            docs_url="https://aistudio.google.com/docs/models",
        ),
        Provider(
            "deepseek",
            "DeepSeek",
            "api",
            "DeepSeek chat and reasoning models.",
            ("deepseek-flash", "deepseek-v4-pro"),
            key_env=("DEEPSEEK_API_KEY",),
            requires_key=True,
            dependency="openai",
            extra="deepseek",
            docs_url="https://api-docs.deepseek.com/quick_start/pricing",
        ),
        Provider(
            "grok",
            "xAI",
            "api",
            "Grok models through the xAI API.",
            ("grok-4.7", "grok-4.7-latest"),
            key_env=("XAI_API_KEY", "GROK_API_KEY"),
            requires_key=True,
            docs_url="https://docs.x.ai/developers/models",
        ),
        Provider(
            "huggingface",
            "Hugging Face",
            "api",
            "Hosted inference for open model repositories.",
            (
                "Qwen/Qwen3.6-35B-A3B",
                "zai-org/GLM-5.3",
                "zai-org/GLM-5.3-Flash",
                "moonshotai/Kimi-K2.6",
                "openai/gpt-oss-120b",
            ),
            key_env=("HF_API_TOKEN",),
            requires_key=True,
            dependency="huggingface_hub",
            extra="huggingface",
            docs_url="https://huggingface.co/inference/models",
        ),
        Provider(
            "openai-compatible",
            "OpenAI compatible",
            "api",
            "Connect a custom hosted or local endpoint.",
            base_url="http://127.0.0.1:1234/v1",
            key_env=("OPENAI_COMPATIBLE_API_KEY",),
            docs_url="https://github.com/nMaroulis/protolink",
        ),
        Provider(
            "ollama",
            "Ollama",
            "local",
            "Use a model running in Ollama.",
            ("gemma4:e4b", "gemma4:12b", "qwen3:8b", "llama3.3:70b"),
            "http://127.0.0.1:11434",
            ("OLLAMA_API_KEY",),
            docs_url="https://ollama.com/library",
        ),
        Provider(
            "lmstudio",
            "LM Studio",
            "local",
            "Connect to the LM Studio local server.",
            ("local-model", "qwen3.5-35b-a3b", "llama-3.3-70b-instruct"),
            "http://127.0.0.1:1234/v1",
            ("LMSTUDIO_API_KEY",),
            docs_url="https://lmstudio.ai/docs",
        ),
        Provider(
            "vllm",
            "vLLM",
            "local",
            "Use an existing vLLM inference server.",
            ("Qwen/Qwen3.5-35B-A3B", "meta-llama/Llama-3.3-70B-Instruct"),
            "http://127.0.0.1:8000/v1",
            ("VLLM_API_KEY",),
            docs_url="https://docs.vllm.ai",
        ),
        Provider(
            "llama.cpp-server",
            "llama.cpp server",
            "local",
            "Connect to an existing llama.cpp server.",
            ("local-model", "gemma4:e4b"),
            "http://127.0.0.1:8080",
            docs_url="https://github.com/ggml-org/llama.cpp/tree/master/tools/server",
        ),
        Provider(
            "llama.cpp-local",
            "llama.cpp embedded",
            "local",
            "Load a GGUF file directly on the Python server.",
            dependency="llama_cpp",
            extra="llama-cpp",
            docs_url="https://llama-cpp-python.readthedocs.io",
        ),
        Provider(
            "mock",
            "Mock runtime",
            "local",
            "Test the agent pipeline with a simulated model response.",
            ("mock-gpt",),
            docs_url="https://github.com/nMaroulis/protolink",
        ),
    ]
}


# Published API model context sizes. A hosting route can impose a lower cap.
API_CONTEXT_WINDOWS = {
    "openai": {
        "gpt-6.2-sol": 1_050_000,
        "gpt-6.2-astra": 1_050_000,
        "gpt-6.1-terra": 1_050_000,
        "gpt-6-luna": 1_050_000,
        "gpt-6.1-sol": 1_050_000,
        "gpt-4.1-mini": 1_047_576,
    },
    "anthropic": dict.fromkeys(PROVIDERS["anthropic"].models, 1_000_000),
    "gemini": dict.fromkeys(PROVIDERS["gemini"].models, 1_048_576),
    "deepseek": dict.fromkeys(PROVIDERS["deepseek"].models, 1_000_000),
    "grok": dict.fromkeys(PROVIDERS["grok"].models, 500_000),
    "huggingface": {
        "Qwen/Qwen3.6-35B-A3B": 262_144,
        "zai-org/GLM-5.3": 1_048_576,
        "zai-org/GLM-5.3-Flash": 1_048_576,
        "moonshotai/Kimi-K2.6": 262_144,
        "openai/gpt-oss-120b": 131_072,
    },
}

# Names accepted by each installed ProtoLink adapter. Its Hugging Face
# implementation does not forward a reply token limit in 0.8.4.
API_OUTPUT_PARAMETERS = {
    "openai": "max_output_tokens",
    "anthropic": "max_tokens",
    "gemini": "max_output_tokens",
    "deepseek": "max_tokens",
    "grok": "max_tokens",
    "openai-compatible": "max_tokens",
}


def published_context_window(provider: str, model: str) -> int | None:
    """Return the catalog limit for a known model, without probing an inference endpoint."""
    if provider == "openai":
        model = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)
    elif provider == "huggingface":
        model = model.partition(":")[0]
    return API_CONTEXT_WINDOWS.get(provider, {}).get(model)
