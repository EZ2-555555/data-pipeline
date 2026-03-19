"""SQS message queue for decoupling ingestion from embedding.

After ingestion writes raw documents to S3 and the DB, it sends an
SQS message containing the document ID and S3 key. The embedding
pipeline polls SQS, processes each message, and deletes it on success.

Falls back to direct (synchronous) pipeline execution when SQS is
unavailable (local dev without LocalStack).
"""

import json
import logging
import os

from src.config import settings

logger = logging.getLogger(__name__)


def _get_sqs_client():
    """Return a boto3 SQS client, or None when running without AWS."""
    if not settings.SQS_ENABLED:
        return None
    try:
        import boto3

        kwargs = {"region_name": settings.AWS_REGION}
        endpoint = os.getenv("SQS_ENDPOINT_URL")  # LocalStack
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        return boto3.client("sqs", **kwargs)
    except Exception:
        logger.debug("SQS client unavailable — falling back to direct pipeline")
        return None


# ---------------------------------------------------------------------------
# Producer side (called by ingesters)
# ---------------------------------------------------------------------------

def send_document_message(document_id: int, s3_key: str, source: str) -> bool:
    """Send a processing message to the ingestion queue.

    Returns True if the message was sent, False if SQS is unavailable
    (caller should fall back to synchronous processing).
    """
    client = _get_sqs_client()
    queue_url = settings.SQS_QUEUE_URL
    if not client or not queue_url:
        return False

    body = json.dumps({
        "document_id": document_id,
        "s3_key": s3_key,
        "source": source,
    })

    kwargs = {"QueueUrl": queue_url, "MessageBody": body}
    if queue_url.endswith(".fifo"):
        kwargs["MessageGroupId"] = source
    client.send_message(**kwargs)
    logger.debug("SQS message sent: doc_id=%d key=%s", document_id, s3_key)
    return True


def send_batch(messages: list[dict]) -> int:
    """Send up to 10 messages in a batch. Returns count sent."""
    client = _get_sqs_client()
    queue_url = settings.SQS_QUEUE_URL
    if not client or not queue_url or not messages:
        return 0

    entries = []
    is_fifo = queue_url.endswith(".fifo")
    for i, msg in enumerate(messages[:10]):
        entry = {
            "Id": str(i),
            "MessageBody": json.dumps(msg),
        }
        if is_fifo:
            entry["MessageGroupId"] = msg.get("source", "default")
        entries.append(entry)

    resp = client.send_message_batch(QueueUrl=queue_url, Entries=entries)
    failed = resp.get("Failed", [])
    if failed:
        logger.warning("SQS batch: %d/%d messages failed", len(failed), len(entries))
    sent = len(entries) - len(failed)
    logger.debug("SQS batch sent: %d messages", sent)
    return sent


# ---------------------------------------------------------------------------
# Consumer side (called by pipeline / Lambda)
# ---------------------------------------------------------------------------

def receive_messages(max_messages: int = 5, wait_seconds: int = 5) -> list[dict]:
    """Poll SQS for processing messages.

    Returns a list of dicts with 'body' (parsed JSON) and 'receipt_handle'.
    Returns empty list if SQS is unavailable.
    """
    client = _get_sqs_client()
    queue_url = settings.SQS_QUEUE_URL
    if not client or not queue_url:
        return []

    resp = client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=min(max_messages, 10),
        WaitTimeSeconds=wait_seconds,
    )

    messages = []
    for msg in resp.get("Messages", []):
        try:
            body = json.loads(msg["Body"])
        except (json.JSONDecodeError, KeyError):
            logger.warning("Skipping malformed SQS message: %s", msg.get("MessageId"))
            continue
        messages.append({
            "body": body,
            "receipt_handle": msg["ReceiptHandle"],
            "message_id": msg["MessageId"],
        })

    return messages


def delete_message(receipt_handle: str) -> None:
    """Delete a successfully processed message from the queue."""
    client = _get_sqs_client()
    queue_url = settings.SQS_QUEUE_URL
    if not client or not queue_url:
        return

    client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
