"""Document AI batch_process_documents (GCS in → GCS JSON out)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.pipelines.document_ai_client import document_processor_client
from ai.pipelines.document_ai_parser import (
    TOKEN_SOURCE_DOCUMENT_AI,
    document_ai_document_to_words,
    document_payload,
)
from ai.pipelines.document_text_extraction import ExtractedDocument, PositionedWord, SourceFormat
from config import document_ai_configured, settings
from services.document_ai_storage import (
    gcs_uri,
    list_blob_names,
    split_gcs_uri,
    upload_pdf,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchJobResult:
    """Output of a completed batch job."""

    input_gcs_uri: str
    output_gcs_prefix: str
    output_blob_names: tuple[str, ...]
    words: tuple[PositionedWord, ...]


def _processor_resource_name() -> str:
    processor_id = settings.document_ai_processor_id
    if not processor_id:
        raise ValueError("DOCUMENT_AI_PROCESSOR_ID is not set")
    return processor_id.strip()


def _output_bucket() -> str:
    bucket = settings.document_ai_gcs_output_bucket
    if not bucket:
        raise ValueError("DOCUMENT_AI_GCS_OUTPUT_BUCKET is not set")
    return bucket


def start_batch_process(
    *,
    input_gcs_uri: str,
    output_gcs_prefix: str,
    mime_type: str = "application/pdf",
) -> Any:
    """Start ``batch_process_documents``; returns a long-running operation."""
    from google.cloud import documentai

    if not document_ai_configured():
        raise RuntimeError("Document AI is not fully configured (see config.document_ai_configured)")

    location = settings.document_ai_location
    client = document_processor_client(location)

    output_prefix = output_gcs_prefix.rstrip("/") + "/"
    if not output_prefix.startswith("gs://"):
        output_prefix = gcs_uri(_output_bucket(), output_prefix.removeprefix("gs://"))

    request = documentai.BatchProcessRequest(
        name=_processor_resource_name(),
        input_documents=documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(
                documents=[
                    documentai.GcsDocument(
                        gcs_uri=input_gcs_uri,
                        mime_type=mime_type,
                    )
                ]
            )
        ),
        document_output_config=documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=output_prefix,
            )
        ),
    )
    return client.batch_process_documents(request=request)


def wait_for_batch_operation(operation: Any, *, timeout_seconds: float = 3600.0) -> None:
    """Block until the batch LRO completes or raises."""
    operation.result(timeout=timeout_seconds)


def output_prefix_for_job(job_id: str | None = None) -> str:
    """Default GCS output prefix under the configured output bucket."""
    jid = job_id or uuid.uuid4().hex
    bucket = _output_bucket()
    return gcs_uri(bucket, f"batch-output/{jid}/")


def list_output_json_blobs(output_gcs_prefix: str) -> list[str]:
    """List JSON object names under a batch output prefix."""
    bucket, prefix = split_gcs_uri(output_gcs_prefix.rstrip("/") + "/")
    names = list_blob_names(bucket_name=bucket, prefix=prefix)
    return [n for n in names if n.lower().endswith(".json")]


def words_from_output_blobs(
    output_gcs_prefix: str,
    *,
    bucket_name: str | None = None,
) -> list[PositionedWord]:
    """Download and parse all JSON shards under an output prefix."""
    from services.document_ai_storage import download_bytes

    bucket = bucket_name or _output_bucket()
    _, prefix = split_gcs_uri(output_gcs_prefix.rstrip("/") + "/")
    words: list[PositionedWord] = []
    for blob_name in list_output_json_blobs(output_gcs_prefix):
        raw = download_bytes(bucket_name=bucket, object_name=blob_name)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("Skipping non-JSON blob %s", blob_name)
            continue
        if not isinstance(data, dict):
            continue
        doc = document_payload(data)
        words.extend(document_ai_document_to_words(doc, token_source=TOKEN_SOURCE_DOCUMENT_AI))
    return words


def batch_extract_words_from_pdf(
    local_pdf_path: str | Path,
    *,
    timeout_seconds: float = 3600.0,
    job_id: str | None = None,
) -> BatchJobResult:
    """Upload PDF, run batch OCR, poll, parse tokens — end-to-end."""
    path = Path(local_pdf_path)
    input_uri = upload_pdf(path)
    out_prefix = output_prefix_for_job(job_id)
    operation = start_batch_process(input_gcs_uri=input_uri, output_gcs_prefix=out_prefix)
    wait_for_batch_operation(operation, timeout_seconds=timeout_seconds)
    blob_names = list_output_json_blobs(out_prefix)
    words = words_from_output_blobs(out_prefix)
    return BatchJobResult(
        input_gcs_uri=input_uri,
        output_gcs_prefix=out_prefix,
        output_blob_names=tuple(blob_names),
        words=tuple(words),
    )


def batch_result_to_extracted_document(result: BatchJobResult) -> ExtractedDocument:
    """Wrap batch tokens in ``ExtractedDocument`` for merge/index code."""
    words = list(result.words)
    page_count = max((w.page_index for w in words), default=-1) + 1
    if page_count <= 0:
        page_count = 1
    return ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=page_count,
        words=words,
    )
