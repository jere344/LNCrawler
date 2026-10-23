"""Settings for tests that configure the LLM fallback chain (services/llm_service.py)."""


def llm_chain(name="groq", **caps):
    """``override_settings`` kwargs that make ``name`` the only provider of the chain.

    ``caps`` overrides the provider's fields, e.g. ``daily_tokens=1000`` or ``api_key=""``.
    """
    entry = {
        "api_key": "key",
        "model": "m",
        "base_url": "",
        "reasoning_effort": "",
        "daily_requests": None,
        "daily_tokens": None,
        "requests_per_minute": None,
        "tokens_per_minute": None,
        "cooldown": 60,
        "extra_body": {},
        "json_schema": True,
    }
    entry.update(caps)
    return {"LLM_PROVIDERS": [name], "LLM_PROVIDER_SETTINGS": {name: entry}}
