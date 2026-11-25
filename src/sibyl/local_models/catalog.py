"""Read model catalogs from configured local servers without running inference."""

import json
from typing import Literal

import httpx

from sibyl.services.workspace.llm_settings import ModelSettings, ModelSettingsRequest

CatalogProvider = Literal["lmstudio", "vllm", "llama.cpp-server"]
MAX_CATALOG_BYTES = 512 * 1024


def check_catalog(settings: ModelSettings, provider: CatalogProvider, *, transport=None) -> dict:
    """Send a bounded, credential-scoped catalog read to a local model profile."""
    return read_catalog(settings.provider_config(provider), transport=transport)


def read_catalog(profile: dict, *, transport=None) -> dict:
    """Read a single saved server's catalog using its own credential."""
    provider = profile["provider"]
    base = ModelSettingsRequest(
        provider=provider, model="catalog-check", base_url=profile["base_url"]
    ).base_url.rstrip("/")
    # The paths match ProtoLink's model server adapters.
    path = "/models" if provider != "llama.cpp-server" and base.endswith("/v1") else "/v1/models"
    headers = {"Authorization": f"Bearer {profile['api_key']}"} if profile["api_key"] else {}
    try:
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False, transport=transport) as client:
            with client.stream("GET", base + path, headers=headers) as response:
                if response.status_code in {401, 403}:
                    return {
                        "status": "unauthorized",
                        "models": [],
                        "error": "Check the saved server API key.",
                    }
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise ValueError("Catalog is too large.")
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Invalid model catalog.")
        names = list(
            dict.fromkeys(
                row["id"]
                for row in payload["data"]
                if isinstance(row, dict) and isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 500
            )
        )
        return {"status": "running", "models": [{"name": name} for name in names], "error": None}
    except httpx.RequestError:
        return {
            "status": "unreachable",
            "models": [],
            "error": "Check that the server is running and its URL is reachable.",
        }
    except (httpx.HTTPStatusError, ValueError):
        return {
            "status": "catalog_unavailable",
            "models": [],
            "error": "The server did not return a usable model catalog. Check its URL and provider setup.",
        }
