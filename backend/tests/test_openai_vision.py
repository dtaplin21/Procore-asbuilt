from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.pipelines.openai_vision import (
    encode_image_as_data_url,
    extract_plain_text_from_image,
)


def test_encode_image_as_data_url_uses_base64_payload() -> None:
    data_url = encode_image_as_data_url(b"abc", "image/png")

    assert data_url.startswith("data:image/png;base64,")
    assert data_url.endswith("YWJj")


@patch("ai.pipelines.openai_vision._vision_chat_completion")
def test_extract_plain_text_from_image_reads_file_and_calls_vision(
    mock_vision: MagicMock,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    mock_vision.return_value = "INSPECTION REPORT\nLine 2"

    text = extract_plain_text_from_image(file_path=image_path)

    assert text == "INSPECTION REPORT\nLine 2"
    mock_vision.assert_called_once()
    data_url = mock_vision.call_args.kwargs["image_data_url"]
    assert data_url.startswith("data:image/png;base64,")


@patch("ai.pipelines.openai_vision._vision_chat_completion")
def test_extract_plain_text_from_image_accepts_bytes(mock_vision: MagicMock) -> None:
    mock_vision.return_value = "Photo caption"

    text = extract_plain_text_from_image(image_bytes=b"jpeg-bytes", mime_type="image/jpeg")

    assert text == "Photo caption"
    data_url = mock_vision.call_args.kwargs["image_data_url"]
    assert data_url.startswith("data:image/jpeg;base64,")
