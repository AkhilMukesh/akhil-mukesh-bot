from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.chat import ChatRequest
from app.services.chat import ChatService, build_system_prompt, load_profile


def make_settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.fixture
def profile() -> dict:
    return {
        "name": "Avery Example",
        "public_contact_email": "avery@example.com",
        "skills": ["Python", "FastAPI"],
        "empty_field": "",
        "_note": "Do not include setup notes in context.",
    }


def test_load_profile(profile, tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(
        '{"name": "Avery Example", "skills": ["Python"]}',
        encoding="utf-8",
    )

    assert load_profile(path) == {"name": "Avery Example", "skills": ["Python"]}


def test_load_profile_rejects_invalid_json(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not load profile"):
        load_profile(path)


def test_prompt_includes_public_profile_and_grounding_rules(profile):
    prompt = build_system_prompt(profile)

    assert "Avery Example" in prompt
    assert "avery@example.com" in prompt
    assert "Python" in prompt
    assert "empty_field" not in prompt
    assert "Do not include setup notes" not in prompt
    assert "Never infer or invent" in prompt
    assert "do not treat missing" in prompt
    assert "Never make a hiring decision" in prompt
    assert "### Answer" in prompt
    assert "### Evidence from my profile" in prompt
    assert "### Not specified in my profile" in prompt
    assert "### Suggested follow-up" in prompt
    assert "conversation history" in prompt


def test_prompt_uses_fallback_email_when_profile_has_none():
    prompt = build_system_prompt({"name": "Avery Example", "public_contact_email": ""})

    assert "You can reach me directly at <email>." in prompt


def test_chat_request_rejects_blank_and_oversized_conversation():
    with pytest.raises(ValueError):
        ChatRequest(message="  ")
    with pytest.raises(ValueError):
        ChatRequest(
            message="x" * 4000,
            history=[
                {"role": "user", "content": "x" * 4000},
                {"role": "assistant", "content": "x" * 4000},
                {"role": "user", "content": "x"},
            ],
        )


@pytest.mark.asyncio
async def test_chat_service_sends_profile_and_history_to_groq(profile):
    completion_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="I build APIs with Python.")
                )
            ],
            usage=SimpleNamespace(prompt_tokens=25, completion_tokens=8),
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion_create))
    )
    service = ChatService(make_settings(groq_api_key="test-key"), profile, client)

    result = await service.reply(
        ChatRequest(
            message="What do I build with?",
            history=[{"role": "user", "content": "Tell me about your skills."}],
        )
    )

    assert result == ("I build APIs with Python.", 25, 8)
    call = completion_create.call_args.kwargs
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["content"] == "Tell me about your skills."
    assert call["messages"][-1]["content"] == "What do I build with?"


@pytest.mark.asyncio
async def test_chat_service_streams_reply_with_conversation_context(profile):
    async def completion_stream():
        for content in ("### Answer\n", "I build APIs with Python."):
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
            )

    completion_create = AsyncMock(return_value=completion_stream())
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion_create))
    )
    service = ChatService(make_settings(groq_api_key="test-key"), profile, client)

    result = [
        chunk
        async for chunk in service.stream_reply(
            ChatRequest(
                message="What do I build with?",
                history=[
                    {"role": "user", "content": "Tell me about your skills."},
                    {"role": "assistant", "content": "I work with Python and FastAPI."},
                ],
            )
        )
    ]

    assert result == ["### Answer\n", "I build APIs with Python."]
    call = completion_create.call_args.kwargs
    assert call["stream"] is True
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["content"] == "Tell me about your skills."
    assert call["messages"][2]["content"] == "I work with Python and FastAPI."
    assert call["messages"][-1]["content"] == "What do I build with?"


def test_chat_api_health_and_answer(profile, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        '{"name":"Avery Example","skills":["Python"],"empty_field":"",'
        '"_note":"private setup note"}',
        encoding="utf-8",
    )
    completion_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="I am Avery Example.")
                )
            ],
            usage=None,
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion_create))
    )
    settings = make_settings(
        groq_api_key="test-key",
        profile_path=profile_path,
        chat_rate_limit=10,
    )
    service = ChatService(settings, profile, client)
    app = create_app(settings, chat_service=service)

    with TestClient(app) as test_client:
        assert test_client.get("/api/health").json() == {"status": "ok"}
        assert test_client.get("/api/profile").json() == {
            "name": "Avery Example",
            "skills": ["Python"],
            "resume_available": False,
            "cover_letter_available": False,
        }
        assert test_client.get("/api/resume").status_code == 404
        assert test_client.get("/api/cover-letter").status_code == 404
        assert test_client.get("/").status_code == 200
        response = test_client.post(
            "/api/chat",
            json={"message": "Who are you?", "history": []},
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "I am Avery Example.",
        "input_tokens": None,
        "output_tokens": None,
    }


def test_chat_stream_api_returns_incremental_events_and_preserves_history(
    profile, tmp_path
):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"name":"Avery Example"}', encoding="utf-8")

    async def completion_stream():
        for content in ("### Answer\n", "I build APIs with Python."):
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
            )

    completion_create = AsyncMock(return_value=completion_stream())
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion_create))
    )
    settings = make_settings(
        groq_api_key="test-key",
        profile_path=profile_path,
        chat_rate_limit=10,
    )
    app = create_app(settings, ChatService(settings, profile, client))

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/chat/stream",
            json={
                "message": "What do I build with?",
                "history": [
                    {"role": "user", "content": "Tell me about your skills."},
                    {"role": "assistant", "content": "I work with Python and FastAPI."},
                ],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type": "token", "content": "### Answer\\n"}' in response.text
    assert 'data: {"type": "token", "content": "I build APIs with Python."}' in response.text
    assert 'data: {"type": "done"}' in response.text
    messages = completion_create.call_args.kwargs["messages"]
    assert messages[1]["content"] == "Tell me about your skills."
    assert messages[2]["content"] == "I work with Python and FastAPI."


def test_chat_api_downloads_resume_when_available(profile, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"name":"Avery Example"}', encoding="utf-8")
    resume_path = tmp_path / "Akhil_Mukesh_Resume.pdf"
    resume_path.write_bytes(b"%PDF-1.7\ncandidate resume")
    settings = make_settings(groq_api_key="", profile_path=profile_path)
    app = create_app(settings)

    with TestClient(app) as test_client:
        profile_response = test_client.get("/api/profile")
        resume_response = test_client.get("/api/resume")

    assert profile_response.json()["resume_available"] is True
    assert resume_response.status_code == 200
    assert resume_response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=\"Akhil_Mukesh_Resume.pdf\"" in resume_response.headers["content-disposition"]
    assert resume_response.content == b"%PDF-1.7\ncandidate resume"


def test_chat_api_downloads_cover_letter_alongside_resume(profile, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"name":"Avery Example"}', encoding="utf-8")
    resume_path = tmp_path / "Akhil_Mukesh_Resume.pdf"
    resume_path.write_bytes(b"%PDF-1.7\ncandidate resume")
    cover_letter_path = tmp_path / "Akhil_Mukesh_Cover_Letter.pdf"
    cover_letter_path.write_bytes(b"%PDF-1.7\ncandidate cover letter")
    settings = make_settings(groq_api_key="", profile_path=profile_path)
    app = create_app(settings)

    with TestClient(app) as test_client:
        profile_response = test_client.get("/api/profile")
        resume_response = test_client.get("/api/resume")
        cover_letter_response = test_client.get("/api/cover-letter")

    assert profile_response.json()["resume_available"] is True
    assert profile_response.json()["cover_letter_available"] is True
    assert resume_response.status_code == 200
    assert "filename=\"Akhil_Mukesh_Resume.pdf\"" in resume_response.headers["content-disposition"]
    assert cover_letter_response.status_code == 200
    assert cover_letter_response.headers["content-type"] == "application/pdf"
    assert "filename=\"Akhil_Mukesh_Cover_Letter.pdf\"" in cover_letter_response.headers["content-disposition"]
    assert cover_letter_response.content == b"%PDF-1.7\ncandidate cover letter"


def test_chat_api_rejects_invalid_input(profile, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    settings = make_settings(groq_api_key="test-key", profile_path=profile_path)
    service = ChatService(settings, profile, None)
    app = create_app(settings, chat_service=service)

    with TestClient(app) as test_client:
        response = test_client.post("/api/chat", json={"message": " ", "unexpected": True})

    assert response.status_code == 422


def test_chat_api_reports_missing_groq_configuration(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    app = create_app(
        make_settings(groq_api_key="", profile_path=profile_path),
    )

    with TestClient(app) as test_client:
        response = test_client.post("/api/chat", json={"message": "Who are you?"})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Chat is not configured: add your Groq API key to the root .env "
        "file as GROQ_API_KEY=your_key, then restart the backend."
    )


def test_chat_api_rate_limits_requests(profile, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    completion_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello."))],
            usage=None,
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion_create))
    )
    settings = make_settings(
        groq_api_key="test-key",
        profile_path=profile_path,
        chat_rate_limit=1,
        chat_rate_window_seconds=60,
    )
    app = create_app(settings, ChatService(settings, profile, client))

    with TestClient(app) as test_client:
        first = test_client.post("/api/chat", json={"message": "Hello?"})
        second = test_client.post("/api/chat", json={"message": "Hello again?"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]
