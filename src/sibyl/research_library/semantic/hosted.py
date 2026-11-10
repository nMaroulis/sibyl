"""Reviewed hosted embedding clients using ProtoLink's native OpenAIEmbedder.

ProtoLink adapts the actual SDK client and orders its returned vectors. Sibyl
checks provider/model/batch identity before that conversion loses response IDs,
and owns explicit consent, local credential storage and index revision fences.
There are no provider calls or SDK imports at startup. Hosted names/dimensions
are observed identities, not attested model weights or calibrated relevance.
"""

import asyncio
import json
from importlib.util import find_spec

import httpx
from protolink.rag import OpenAIEmbedder

from sibyl.research_library.semantic.contracts import SemanticNotReady
from sibyl.research_library.semantic.provider import normalized

PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "endpoint": "https://api.openai.com/v1",
        "models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
    },
    "mistral": {"label": "Mistral", "endpoint": "https://api.mistral.ai/v1", "models": ["mistral-embed"]},
}
INSTALL = "uv pip install 'sibyl[openai]'"


def provider_spec(provider, model):
    """Permit only reviewed official origins and model names; never accept a secret-bearing URL."""
    spec = PROVIDERS.get(provider)
    if not spec or model not in spec["models"]:
        raise SemanticNotReady("Choose one of this provider's supported embedding models.")
    return spec


def catalog():
    """Read optional SDK availability without constructing a client or contacting any provider."""
    available = find_spec("openai") is not None
    return {
        "items": [{"id": name, **spec, "available": available} for name, spec in PROVIDERS.items()],
        "install": INSTALL,
    }


class CheckedClient:
    """Check the SDK receipt before native adaptation, preserving exact passage-to-vector alignment."""

    def __init__(self, client):
        self.client = client
        self.embeddings = self

    async def create(self, **kwargs):
        # SDK parsing can coerce boolean/string coordinates and indices. Check
        # bounded raw JSON first, then let ProtoLink adapt/order the valid batch.
        async with self.client.embeddings.with_streaming_response.create(
            **kwargs, encoding_format="float"
        ) as response:
            chunks, size = [], 0
            async for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    raise ValueError("The hosted embedding response exceeds 8 MiB.")
                chunks.append(chunk)
            result = json.loads(b"".join(chunks))
        count = len(kwargs["input"])
        if (
            not isinstance(result, dict)
            or result.get("model") != kwargs["model"]
            or not isinstance(result.get("data"), list)
            or len(result["data"]) != count
        ):
            raise ValueError("The embedding provider returned a different model or an incomplete batch.")
        indices = [item.get("index") for item in result["data"] if isinstance(item, dict)]
        if (
            len(indices) != count
            or any(type(i) is not int for i in indices)
            or set(indices) != set(range(count))
        ):
            raise ValueError("The embedding provider returned ambiguous batch indices.")
        for item in result["data"]:
            normalized(item.get("embedding"))
        return result


class HostedEmbeddings:
    """One bounded, single-attempt request through a native ProtoLink embedder and explicit SDK lifecycle."""

    def __init__(self, client_factory=None):
        self.client_factory = client_factory or self.sdk_client

    @staticmethod
    def sdk_client(api_key, endpoint):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise SemanticNotReady(f"Install the hosted embedding dependency: {INSTALL}") from None
        return AsyncOpenAI(
            api_key=api_key,
            organization="",
            project="",
            base_url=endpoint,
            max_retries=0,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(30, connect=3), trust_env=False, follow_redirects=False
            ),
        )

    def embed(self, profile, texts, api_key):
        """Embed explicit passage/query text; credentials stay application-private and errors are safe."""
        spec = provider_spec(profile["provider"], profile["model"])
        if (
            profile.get("endpoint", spec["endpoint"]) != spec["endpoint"]
            or profile.get("remote_consent") is not True
        ):
            raise SemanticNotReady(
                "Review and enable hosted text processing before sending embedding requests."
            )
        if (
            not api_key
            or not 1 <= len(texts) <= 32
            or any(not isinstance(t, str) or not t.strip() or len(t) > 1600 for t in texts)
        ):
            raise ValueError(
                "Embed one to thirty-two nonempty passages of at most 1,600 characters with a saved provider key."
            )
        try:
            raw = asyncio.run(self._embed(spec["endpoint"], profile["model"], texts, api_key))
            vectors = [normalized(row) for row in raw]
            dimensions = len(vectors[0])
            if (
                any(len(row) != dimensions for row in vectors)
                or profile.get("dimensions", dimensions) != dimensions
            ):
                raise SemanticNotReady(
                    "Hosted embedding dimensions changed. Check the model and rebuild its index."
                )
        except SemanticNotReady:
            raise
        except Exception:
            # SDK status/error bodies may repeat input or credentials; never expose them to API/agents.
            raise ValueError(
                "The hosted embedding request failed. Check provider access, model, quota and dimensions. No retry, truncation or local substitution was performed."
            ) from None
        return {
            "provider": profile["provider"],
            "endpoint": spec["endpoint"],
            "model": profile["model"],
            "dimensions": dimensions,
            "remote_consent": True,
            "identity": "Hosted model name and dimensions; weight changes cannot be independently detected.",
        }, vectors

    async def _embed(self, endpoint, model, texts, api_key):
        async with self.client_factory(api_key, endpoint) as client:
            embedder = OpenAIEmbedder(CheckedClient(client), model=model)
            return await embedder.embed_documents(texts)
