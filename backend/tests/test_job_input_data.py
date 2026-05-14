import pytest

from services.job_input_data import coerce_job_int


def test_coerce_job_int_accepts_str() -> None:
    assert coerce_job_int("42", "drawing_id") == 42


def test_coerce_job_int_rejects_bool() -> None:
    with pytest.raises(ValueError, match="boolean"):
        coerce_job_int(True, "drawing_id")
