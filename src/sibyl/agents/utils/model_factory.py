"""Construct ProtoLink models with Sibyl's provider compatibility defaults."""

from protolink import create_llm as create_protolink_llm


def create_llm(provider: str, **kwargs):
    """Leave OpenAI's sampling defaults to the Responses API."""
    if provider == "openai":
        from openai import omit

        # ProtoLink 0.8.4 merges these into every Responses request. Modern
        # reasoning models reject them; the SDK's public sentinel omits them.
        kwargs["model_params"] = {
            "temperature": omit,
            "top_p": omit,
            "top_logprobs": omit,
            **(kwargs.get("model_params") or {}),
        }
    return create_protolink_llm(provider, **kwargs)
