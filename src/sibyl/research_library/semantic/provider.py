"""Bounded native Ollama embedding calls; no chat SDK, downloads, credentials or redirects."""

import json
import re

import httpx
import numpy as np

from sibyl.research_library.semantic.contracts import LocalEndpoint, SemanticNotReady

MAX_RESPONSE = 8 * 1024 * 1024


def normalized(vector):
    """Accept finite numeric coordinates and retain a portable unit float32 vector."""
    if not isinstance(vector, list) or not 1 <= len(vector) <= 4096:
        raise ValueError("The embedding model returned unsupported vector dimensions (maximum 4,096).")
    if any(type(x) not in {int, float} for x in vector):
        raise ValueError("The embedding model returned non-numeric coordinates.")
    raw = np.asarray(vector, dtype=np.float64)
    if not np.isfinite(raw).all() or np.max(np.abs(raw)) > 1e6:
        raise ValueError("The embedding model returned invalid coordinates.")
    norm = float(np.linalg.norm(raw))
    if not norm > 0:
        raise ValueError("The embedding model returned an empty-direction vector.")
    return (raw / norm).astype("<f4")


class OllamaEmbeddings:
    """Inspect observed model identity on both sides of each explicit embedding call.

    The local server is a trusted component. Remote/cloud models advertised by
    Ollama are rejected. Digest/version checks detect observed changes, not an
    independently attested or atomic model-name binding at the server.
    """

    def __init__(self, client_factory=None):
        self.client_factory = client_factory or (
            lambda: httpx.Client(
                timeout=httpx.Timeout(30, connect=2), trust_env=False, follow_redirects=False
            )
        )

    def _read(self, client, endpoint, path, body=None):
        try:
            with client.stream("GET" if body is None else "POST", endpoint + path, json=body) as response:
                if not response.is_success:
                    raise ValueError(
                        "Local Ollama could not complete the embedding request. Check the installed model, input length and server status. No text was truncated or Demo substituted."
                    )
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise ValueError("The local embedding response exceeds 8 MiB.")
                    chunks.append(chunk)
                result = json.loads(b"".join(chunks))
                if not isinstance(result, dict):
                    raise ValueError("Local Ollama returned an unsupported response.")
                return result
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeError):
            raise ValueError(
                "Local Ollama is unavailable or returned an unreadable response. Keyword search remains available."
            ) from None

    @staticmethod
    def canonical(model):
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,179}", model):
            raise ValueError("Choose a valid installed model name.")
        return model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"

    def _models(self, client, endpoint):
        rows = self._read(client, endpoint, "/api/tags").get("models")
        if not isinstance(rows, list) or len(rows) > 1000 or any(not isinstance(r, dict) for r in rows):
            raise ValueError("Local Ollama returned an unsupported model catalog.")
        return rows

    def models(self, endpoint):
        endpoint = LocalEndpoint(endpoint=endpoint).endpoint
        with self.client_factory() as client:
            rows = self._models(client, endpoint)
        return {
            "endpoint": endpoint,
            "items": [
                {"name": row["name"], "remote": bool(row.get("remote_host") or row.get("remote_model"))}
                for row in rows
                if isinstance(row.get("name"), str) and len(row["name"]) <= 180
            ],
        }

    def _describe(self, client, endpoint, model):
        version = self._read(client, endpoint, "/api/version").get("version")
        if not isinstance(version, str) or not 1 <= len(version) <= 80:
            raise ValueError("Local Ollama did not identify its server version.")
        row = next(
            (
                r
                for r in self._models(client, endpoint)
                if self.canonical(r.get("name")) == self.canonical(model)
            ),
            None,
        )
        if not row:
            raise SemanticNotReady(
                "Install the selected embedding model in local Ollama before configuring semantic search."
            )
        shown = self._read(client, endpoint, "/api/show", {"model": model})
        if (
            row.get("remote_host")
            or row.get("remote_model")
            or shown.get("remote_host")
            or shown.get("remote_model")
        ):
            raise SemanticNotReady(
                "The Ollama option supports local models only. Choose the separate hosted OpenAI/Mistral option for remote embeddings."
            )
        if not isinstance(shown.get("capabilities"), list) or "embedding" not in shown["capabilities"]:
            raise SemanticNotReady(
                "Choose an embedding-capable model such as embeddinggemma, rather than a chat model."
            )
        digest = row.get("digest", "")
        if not isinstance(digest, str):
            raise ValueError("Local Ollama did not provide a valid model digest.")
        digest = digest.removeprefix("sha256:")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Local Ollama did not provide a valid model digest.")
        return {
            "endpoint": endpoint,
            "model": self.canonical(model),
            "model_digest": digest,
            "server_version": version,
        }

    def embed(self, profile, texts):
        if not 1 <= len(texts) <= 32 or any(not isinstance(t, str) or not t or len(t) > 1600 for t in texts):
            raise ValueError("Embed one to thirty-two non-empty passages of at most 1,600 characters.")
        endpoint = LocalEndpoint(endpoint=profile["endpoint"]).endpoint
        model = self.canonical(profile["model"])
        with self.client_factory() as client:
            before = self._describe(client, endpoint, model)
            if any(
                profile.get(key) is not None and profile[key] != before[key]
                for key in ("model_digest", "server_version")
            ):
                raise SemanticNotReady(
                    "The embedding model or Ollama version changed. Check and save the model again, then rebuild its index."
                )
            payload = self._read(
                client, endpoint, "/api/embed", {"model": model, "input": texts, "truncate": False}
            )
            if self.canonical(payload.get("model")) != model:
                raise ValueError("Local Ollama returned embeddings for a different model.")
            raw = payload.get("embeddings")
            if not isinstance(raw, list) or len(raw) != len(texts):
                raise ValueError("Local Ollama returned an incomplete embedding batch.")
            vectors = [normalized(v) for v in raw]
            dimension = len(vectors[0])
            if any(len(v) != dimension for v in vectors) or profile.get("dimensions", dimension) != dimension:
                raise SemanticNotReady(
                    "Embedding dimensions changed. Check and save the model again before rebuilding."
                )
            if before != self._describe(client, endpoint, model):
                raise SemanticNotReady(
                    "The embedding model changed during this operation. Its results were discarded."
                )
        return {**before, "dimensions": dimension}, vectors
