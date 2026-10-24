from groq import AsyncGroq

from app.config import Settings


def create_groq_client(settings: Settings) -> AsyncGroq:
    return AsyncGroq(
        api_key=settings.groq_api_key.strip(),
        timeout=settings.groq_timeout_seconds,
    )
