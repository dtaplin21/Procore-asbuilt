"""Document AI batch_process_documents (GCS in → GCS JSON out)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai.pipelines.document_ai_client import document_processor_client
from ai.pipelines.document_ai_parser import (
    TOKEN_SOURCE_DOCUMENT_AI,
    document_ai_document_to_words,
    document_payload,
)
from ai.pipelines.document_text_extraction import ExtractedDocument, PositionedWord, SourceFormat
from config import document_ai_configured, settings
from services.document_ai_cache import cached_output_prefix, pdf_content_sha256
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
    content_hash: str | None = None
    cache_hit: bool = False


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
    drawing_id: int | None = None,
    content_hash: str | None = None,
    on_batch_started: Callable[[dict[str, Any]], None] | None = None,
) -> BatchJobResult:
    """Upload PDF, run batch OCR, poll, parse tokens — end-to-end.

    When ``drawing_id`` and ``content_hash`` are set, output is stored under a
    stable prefix; existing JSON shards are reused (no re-batch / re-billing).
    """
    path = Path(local_pdf_path)
    pdf_hash = content_hash or pdf_content_sha256(path)
    out_prefix = (
        cached_output_prefix(drawing_id=int(drawing_id), content_hash=pdf_hash)
        if drawing_id is not None
        else output_prefix_for_job(job_id)
    )

    existing_blobs = list_output_json_blobs(out_prefix)
    if existing_blobs:
        words = words_from_output_blobs(out_prefix)
        logger.info(
            "document_ai_batch_cache_hit",
            extra={
                "drawing_id": drawing_id,
                "content_hash": pdf_hash,
                "output_gcs_prefix": out_prefix,
                "json_shards": len(existing_blobs),
            },
        )
        return BatchJobResult(
            input_gcs_uri="",
            output_gcs_prefix=out_prefix,
            output_blob_names=tuple(existing_blobs),
            words=tuple(words),
            content_hash=pdf_hash,
            cache_hit=True,
        )

    input_uri = upload_pdf(path)
    operation = start_batch_process(input_gcs_uri=input_uri, output_gcs_prefix=out_prefix)
    if on_batch_started is not None:
        op_name = getattr(operation, "operation", None)
        op_name_str = getattr(op_name, "name", None) if op_name is not None else None
        on_batch_started(
            {
                "input_gcs_uri": input_uri,
                "output_gcs_prefix": out_prefix,
                "content_hash": pdf_hash,
                "operation_name": op_name_str,
            }
        )
    wait_for_batch_operation(operation, timeout_seconds=timeout_seconds)
    blob_names = list_output_json_blobs(out_prefix)
    words = words_from_output_blobs(out_prefix)
    return BatchJobResult(
        input_gcs_uri=input_uri,
        output_gcs_prefix=out_prefix,
        output_blob_names=tuple(blob_names),
        words=tuple(words),
        content_hash=pdf_hash,
        cache_hit=False,
    )


def _clip_extracted_document_pages(
    document: ExtractedDocument,
    max_pages: int | None,
) -> ExtractedDocument:
    if max_pages is None or max_pages <= 0 or document.page_count <= max_pages:
        return document
    filtered_words = [word for word in document.words if word.page_index < max_pages]
    return ExtractedDocument(
        source_format=document.source_format,
        page_count=max_pages,
        words=filtered_words,
    )


def extract_document_via_document_ai(
    file_path: str | Path,
    *,
    max_pages: int | None = None,
    timeout_seconds: float | None = None,
    document_ai_stats: dict[str, Any] | None = None,
    drawing_id: int | None = None,
    on_batch_started: Callable[[dict[str, Any]], None] | None = None,
) -> ExtractedDocument:
    """Batch OCR a PDF via Document AI (GCS batch API)."""
    import time

    path = Path(file_path)
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(settings.document_ai_batch_timeout_seconds)
    )
    started = time.monotonic()
    content_hash = pdf_content_sha256(path)
    result = batch_extract_words_from_pdf(
        path,
        timeout_seconds=timeout,
        job_id=path.stem[:64] or None,
        drawing_id=drawing_id,
        content_hash=content_hash,
        on_batch_started=on_batch_started,
    )
    elapsed = time.monotonic() - started
    if document_ai_stats is not None:
        document_ai_stats.update(
            {
                "document_ai_content_hash": result.content_hash or content_hash,
                "document_ai_cache_hit": result.cache_hit,
                "document_ai_input_gcs_uri": result.input_gcs_uri,
                "document_ai_output_gcs_prefix": result.output_gcs_prefix,
                "document_ai_json_shards": len(result.output_blob_names),
                "document_ai_token_count": len(result.words),
                "document_ai_seconds": round(elapsed, 3),
            }
        )
    document = batch_result_to_extracted_document(result)
    return _clip_extracted_document_pages(document, max_pages)


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
