from unittest.mock import Mock

from app.clients.groq_client import create_groq_client
from app.config import Settings


def test_create_groq_client_trims_api_key_whitespace(monkeypatch):
    groq_client = Mock()
    monkeypatch.setattr("app.clients.groq_client.AsyncGroq", groq_client)
    settings = Settings(_env_file=None, groq_api_key=" \r\n test-key \t ")

    create_groq_client(settings)

    groq_client.assert_called_once_with(api_key="test-key", timeout=30.0)
