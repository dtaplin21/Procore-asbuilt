"""OPENAI_API_KEY and OPENAI_CHAT_MODEL loading via Settings."""

from config import Settings


def test_openai_api_key_blank_becomes_none():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        openai_api_key="   ",
    )
    assert s.openai_api_key is None


def test_openai_chat_model_strips_and_defaults_when_empty():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        openai_chat_model="  gpt-4o  ",
    )
    assert s.openai_chat_model == "gpt-4o"


def test_openai_chat_model_default():
    s = Settings(database_url="postgresql://u:p@localhost:5432/db")
    assert s.openai_chat_model == "gpt-4o-mini"
