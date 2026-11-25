"""Check one saved model with a small synthetic request and a safe status."""

import asyncio
from threading import BoundedSemaphore
from urllib.error import HTTPError

import httpx
from protolink import create_llm

from sibyl.agents.utils.model_selection import readiness
from sibyl.agents.utils.providers import PROVIDERS
from sibyl.services.workspace.llm_settings import ModelChoice, ModelSettings

CHECK_TIMEOUT = 20
OUTPUT_TOKENS = 128
CHECK_PROMPT = 'Reply with the JSON object {"ok": true}.'
_slots = BoundedSemaphore(2)


async def check_model(settings: ModelSettings, choice: ModelChoice) -> dict:
    """Verify API inference or embedded setup using only the saved configuration."""
    return await check_configuration(settings.saved_config(choice))


async def check_configuration(config: dict) -> dict:
    """Verify one resolved connection without returning provider payloads."""
    reason = readiness(config)
    if reason:
        return {"status": "needs_setup", "detail": reason}
    provider = config["provider"]
    if provider == "llama.cpp-local":
        return {"status": "configured", "detail": "The GGUF file and its runtime are available."}
    if PROVIDERS[provider].kind != "api":
        raise ValueError("Use the local runtime monitor to check this provider.")
    try:
        return await asyncio.wait_for(asyncio.to_thread(_api_check, config), timeout=CHECK_TIMEOUT)
    except TimeoutError:
        return {"status": "timeout", "detail": "The provider did not respond in time."}


def _api_check(config: dict) -> dict:
    """Limit concurrent SDK calls even if a caller stops waiting for a result."""
    if not _slots.acquire(blocking=False):
        return {"status": "busy", "detail": "Other model checks are running. Try again shortly."}
    try:
        if not _sample(config):
            return {"status": "failed", "detail": "The model returned an empty response."}
        return {"status": "ready", "detail": "The model answered a test request."}
    except Exception as error:
        # Provider errors can contain the full key, request, or remote response.
        response = getattr(error, "response", None)
        status = (
            getattr(error, "status_code", None)
            or getattr(response, "status_code", None)
            or (error.code if isinstance(error, HTTPError) else None)
            or getattr(error, "code", None)
        )
        if status in (401, 403):
            detail = "Check the API key and its permission to use this model."
        elif status == 404:
            detail = "The provider could not find this model for the configured connection."
        elif status in (402, 429):
            detail = "Check the provider's billing, quota, or rate limits."
        else:
            detail = "The provider did not complete the test. Check the model ID and connection."
        return {"status": "failed", "detail": detail}
    finally:
        _slots.release()


def _sample(config: dict) -> str:
    """Send a fixed prompt with no workspace data and a small output allowance."""
    provider, kwargs = ModelSettings.constructor(config)
    messages = [{"role": "user", "content": CHECK_PROMPT}]
    if provider == "huggingface":
        # This ProtoLink adapter does not forward max_tokens to its inference client.
        from huggingface_hub import InferenceClient

        client = InferenceClient(token=config["api_key"], timeout=CHECK_TIMEOUT)
        result = client.chat_completion(messages, model=config["model"], max_tokens=OUTPUT_TOKENS)
        return (result.choices[0].message.content or "").strip() if result.choices else ""
    if provider == "openai-compatible":
        # Do not forward credentials if a user-configured endpoint redirects the check.
        base = config["base_url"].rstrip("/")
        url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
        headers = {"Authorization": f"Bearer {config['api_key']}"} if config["api_key"] else {}
        with httpx.Client(timeout=CHECK_TIMEOUT, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                url,
                headers=headers,
                json={"model": config["model"], "messages": messages, "max_tokens": OUTPUT_TOKENS},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    limit = "max_output_tokens" if provider in {"openai", "gemini"} else "max_tokens"
    model = create_llm(provider, **kwargs, model_params={limit: OUTPUT_TOKENS})
    return (model.chat(CHECK_PROMPT) or "").strip()
