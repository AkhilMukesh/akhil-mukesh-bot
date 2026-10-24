import logging
import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from groq import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError

from app.models.chat import ChatRequest, ChatResponse
from app.services.chat import (
    ChatProviderMisconfigured,
    EmptyCompletionError,
    ChatService,
)
from app.services.rate_limit import RateLimitExceeded


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def log_connection_failure(error: Exception) -> None:
    cause = error.__cause__ or error.__context__
    cause_detail = (
        f"{type(cause).__name__}: {str(cause)[:300]}"
        if cause is not None
        else "no underlying transport detail"
    )
    logger.warning(
        "Groq connection failed: %s; underlying transport error: %s",
        type(error).__name__,
        cause_detail,
    )


async def prepare_chat(request: Request) -> ChatService:
    rate_limiter = request.app.state.rate_limiter
    try:
        await rate_limiter.check(request.client.host if request.client else "unknown")
    except RateLimitExceeded as error:
        logger.info("Client rate limited", extra={"event": "chat_rate_limited"})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You're sending messages too quickly. Please try again shortly.",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error

    chat_service = request.app.state.chat_service
    if chat_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is temporarily unavailable. Please try again later.",
        )
    if chat_service.client is None:
        logger.error(
            "Groq client is not configured",
            extra={"event": "groq_not_configured"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Chat is not configured: add your Groq API key to the root .env "
                "file as GROQ_API_KEY=your_key, then restart the backend."
            ),
        )
    return chat_service


def stream_event(event_type: str, **values: str) -> str:
    return f"data: {json.dumps({'type': event_type, **values}, ensure_ascii=False)}\n\n"


def provider_error_detail(error: Exception) -> str:
    if isinstance(error, ChatProviderMisconfigured):
        return "Chat is not configured. Please contact the site owner."
    if isinstance(error, EmptyCompletionError):
        logger.error("Groq returned no usable streaming answer")
        return "The chat service could not complete your request."
    if isinstance(error, (APITimeoutError, APIConnectionError)):
        log_connection_failure(error)
        return "The chat service is temporarily unavailable. Please try again."
    if isinstance(error, RateLimitError):
        logger.warning("Groq rate limit reached")
        return "The chat service is busy. Please try again shortly."
    if isinstance(error, AuthenticationError):
        logger.error("Groq authentication failed")
        return "The chat service is temporarily misconfigured."
    if isinstance(error, APIStatusError):
        logger.error("Groq API returned status %s", error.status_code)
        return "The chat service could not complete your request."
    raise error


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/profile")
async def profile(request: Request) -> dict:
    candidate_profile = request.app.state.profile
    public_profile = {
        key: value
        for key, value in candidate_profile.items()
        if not key.startswith("_") and value not in ("", [], {}, None)
    }
    public_profile["resume_available"] = request.app.state.resume_path is not None
    public_profile["cover_letter_available"] = (
        request.app.state.cover_letter_path is not None
    )
    return public_profile


@router.get("/resume", response_class=FileResponse)
async def download_resume(request: Request) -> FileResponse:
    resume_path = request.app.state.resume_path
    if resume_path is None or not resume_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The candidate has not added a resume yet.",
        )
    return FileResponse(
        path=resume_path,
        media_type="application/pdf",
        filename=resume_path.name,
    )


@router.get("/cover-letter", response_class=FileResponse)
async def download_cover_letter(request: Request) -> FileResponse:
    cover_letter_path = request.app.state.cover_letter_path
    if cover_letter_path is None or not cover_letter_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The candidate has not added a cover letter yet.",
        )
    return FileResponse(
        path=cover_letter_path,
        media_type="application/pdf",
        filename=cover_letter_path.name,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    chat_service = await prepare_chat(request)

    try:
        answer, input_tokens, output_tokens = await chat_service.reply(payload)
    except ChatProviderMisconfigured as error:
        logger.error(
            "Groq client is not configured",
            extra={"event": "groq_not_configured"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Chat is not configured: add your Groq API key to the root .env "
                "file as GROQ_API_KEY=your_key, then restart the backend."
            ),
        ) from error
    except EmptyCompletionError as error:
        logger.error("Groq returned no usable answer")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The chat service could not complete your request.",
        ) from error
    except (APITimeoutError, APIConnectionError) as error:
        log_connection_failure(error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat service is temporarily unavailable. Please try again.",
        ) from error
    except RateLimitError as error:
        logger.warning("Groq rate limit reached")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat service is busy. Please try again shortly.",
        ) from error
    except AuthenticationError as error:
        logger.error("Groq authentication failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat service is temporarily misconfigured.",
        ) from error
    except APIStatusError as error:
        logger.error("Groq API returned status %s", error.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The chat service could not complete your request.",
        ) from error

    return ChatResponse(
        answer=answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


@router.post("/chat/stream")
async def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    chat_service = await prepare_chat(request)

    async def events():
        try:
            async for content in chat_service.stream_reply(payload):
                yield stream_event("token", content=content)
            yield stream_event("done")
        except (
            ChatProviderMisconfigured,
            EmptyCompletionError,
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            AuthenticationError,
            APIStatusError,
        ) as error:
            yield stream_event("error", detail=provider_error_detail(error))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
