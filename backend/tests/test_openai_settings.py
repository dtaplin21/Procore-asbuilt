"""OPENAI and OCR settings loading via Settings."""

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


def test_openai_vision_model_default():
    s = Settings(database_url="postgresql://u:p@localhost:5432/db")
    assert s.openai_vision_model == "gpt-4o-mini"


def test_openai_vision_model_strips_and_defaults_when_empty():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        openai_vision_model="   ",
    )
    assert s.openai_vision_model == "gpt-4o-mini"


def test_openai_vision_model_strips_whitespace():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        openai_vision_model="  gpt-4o  ",
    )
    assert s.openai_vision_model == "gpt-4o"


def test_ocr_backend_default():
    s = Settings(database_url="postgresql://u:p@localhost:5432/db")
    assert s.ocr_backend == "auto"


def test_ocr_backend_normalizes_case():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        ocr_backend="TESSERACT",
    )
    assert s.ocr_backend == "tesseract"


def test_tesseract_cmd_blank_becomes_none():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        tesseract_cmd="   ",
    )
    assert s.tesseract_cmd is None
