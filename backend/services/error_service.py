from __future__ import annotations


def safe_error_message(exc: Exception, *, fallback: str) -> str:
    """
    Convert internal provider/database errors into messages that are safe for
    users. Keeping this out of Streamlit lets future API routes share the same
    sanitization boundary.
    """
    message = str(exc)
    lowered = message.lower()

    if "llm request failed" in lowered or "missing llm_api_key" in lowered or "openai_api_key" in lowered:
        return "The answer service is unavailable right now. Check the LLM configuration and try again."
    if "search api failed" in lowered or "tavily" in lowered or "brave" in lowered:
        return "External search is unavailable right now. Please try again in a moment."
    if "spotify" in lowered:
        return "Spotify results could not be loaded right now. The answer may still be available."
    if "database" in lowered or "database_url" in lowered or "psycopg" in lowered or "postgres" in lowered:
        return "Account or quota storage is unavailable right now. Please try again shortly."
    return fallback
