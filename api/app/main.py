import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.clients.groq_client import create_groq_client
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.routers.chat import router as chat_router
from app.services.chat import ChatService, load_profile
from app.services.rate_limit import InMemoryRateLimiter


logger = logging.getLogger(__name__)


def find_document(data_dir: Path, document_type: str) -> Optional[Path]:
    preferred_path = data_dir / f"{document_type}.pdf"
    if preferred_path.is_file():
        return preferred_path

    matches = sorted(
        path
        for path in data_dir.glob("*.pdf")
        if document_type in path.stem.casefold()
    )
    return matches[0] if len(matches) == 1 else None


def create_app(
    settings: Optional[Settings] = None,
    chat_service: Optional[ChatService] = None,
) -> FastAPI:
    configure_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        profile = load_profile(app_settings.profile_path)
        app.state.profile = profile
        data_dir = app_settings.profile_path.parent
        app.state.resume_path = find_document(data_dir, "resume")
        app.state.cover_letter_path = find_document(data_dir, "cover_letter")
        managed_client = None
        if chat_service is not None:
            app.state.chat_service = chat_service
        else:
            managed_client = (
                create_groq_client(app_settings) if app_settings.groq_api_key else None
            )
            app.state.chat_service = ChatService(
                settings=app_settings,
                profile=profile,
                client=managed_client,
            )
        app.state.rate_limiter = InMemoryRateLimiter(
            app_settings.chat_rate_limit,
            app_settings.chat_rate_window_seconds,
        )
        logger.info("Akhil Mukesh Bot API started", extra={"event": "application_started"})
        try:
            yield
        finally:
            if managed_client is not None:
                await managed_client.close()
            logger.info("Akhil Mukesh Bot API stopped", extra={"event": "application_stopped"})

    application = FastAPI(
        title="Akhil Mukesh Bot — My AI Representative API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(chat_router)
    application.mount(
        "/",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="frontend",
    )
    return application


app = create_app()
