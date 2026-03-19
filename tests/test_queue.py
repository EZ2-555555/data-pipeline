"""Tests for src/queue/__init__.py — SQS message queue abstraction."""

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _get_sqs_client
# ---------------------------------------------------------------------------

@patch("src.queue.settings")
def test_get_sqs_client_disabled(mock_settings):
    mock_settings.SQS_ENABLED = False
    from src.queue import _get_sqs_client
    assert _get_sqs_client() is None


@patch("src.queue.settings")
def test_get_sqs_client_exception_returns_none(mock_settings):
    mock_settings.SQS_ENABLED = True
    # Simulate boto3.client raising an exception
    mock_boto3 = MagicMock()
    mock_boto3.client.side_effect = Exception("no credentials")
    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        from src.queue import _get_sqs_client
        result = _get_sqs_client()
    assert result is None


# ---------------------------------------------------------------------------
# send_document_message
# ---------------------------------------------------------------------------

@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_document_message_success(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/my-queue"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    from src.queue import send_document_message
    result = send_document_message(42, "raw/hn/key.json", "hn")

    assert result is True
    mock_client.send_message.assert_called_once()
    call_kwargs = mock_client.send_message.call_args[1]
    body = json.loads(call_kwargs["MessageBody"])
    assert body["document_id"] == 42
    assert body["source"] == "hn"


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_document_message_fifo(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/my-queue.fifo"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    from src.queue import send_document_message
    result = send_document_message(1, "key", "arxiv")

    assert result is True
    call_kwargs = mock_client.send_message.call_args[1]
    assert call_kwargs["MessageGroupId"] == "arxiv"


@patch("src.queue._get_sqs_client", return_value=None)
@patch("src.queue.settings")
def test_send_document_message_no_client(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    from src.queue import send_document_message
    assert send_document_message(1, "k", "s") is False


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_document_message_no_queue_url(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = ""
    mock_get_client.return_value = MagicMock()
    from src.queue import send_document_message
    assert send_document_message(1, "k", "s") is False


# ---------------------------------------------------------------------------
# send_batch
# ---------------------------------------------------------------------------

@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_batch_success(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_client.send_message_batch.return_value = {"Failed": []}
    mock_get_client.return_value = mock_client

    from src.queue import send_batch
    messages = [{"document_id": 1, "source": "hn"}, {"document_id": 2, "source": "arxiv"}]
    sent = send_batch(messages)

    assert sent == 2
    mock_client.send_message_batch.assert_called_once()


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_batch_fifo(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue.fifo"
    mock_client = MagicMock()
    mock_client.send_message_batch.return_value = {"Failed": []}
    mock_get_client.return_value = mock_client

    from src.queue import send_batch
    sent = send_batch([{"document_id": 1, "source": "hn"}])
    assert sent == 1

    call_kwargs = mock_client.send_message_batch.call_args[1]
    entry = call_kwargs["Entries"][0]
    assert "MessageGroupId" in entry


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_send_batch_with_failures(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_client.send_message_batch.return_value = {"Failed": [{"Id": "0"}]}
    mock_get_client.return_value = mock_client

    from src.queue import send_batch
    sent = send_batch([{"document_id": 1}, {"document_id": 2}])
    assert sent == 1  # 2 entries - 1 failure


@patch("src.queue._get_sqs_client", return_value=None)
@patch("src.queue.settings")
def test_send_batch_no_client(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "http://queue"
    from src.queue import send_batch
    assert send_batch([{"id": 1}]) == 0


def test_send_batch_empty():
    from src.queue import send_batch
    assert send_batch([]) == 0


# ---------------------------------------------------------------------------
# receive_messages
# ---------------------------------------------------------------------------

@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_receive_messages_success(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {
        "Messages": [
            {
                "Body": '{"document_id": 1}',
                "ReceiptHandle": "rh1",
                "MessageId": "mid1",
            }
        ]
    }
    mock_get_client.return_value = mock_client

    from src.queue import receive_messages
    msgs = receive_messages(max_messages=5, wait_seconds=5)

    assert len(msgs) == 1
    assert msgs[0]["body"]["document_id"] == 1
    assert msgs[0]["receipt_handle"] == "rh1"


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_receive_messages_malformed_json(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {
        "Messages": [
            {"Body": "NOT-JSON", "ReceiptHandle": "rh", "MessageId": "m1"},
        ]
    }
    mock_get_client.return_value = mock_client

    from src.queue import receive_messages
    msgs = receive_messages()
    assert msgs == []  # malformed => skipped


@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_receive_messages_empty(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {}
    mock_get_client.return_value = mock_client

    from src.queue import receive_messages
    assert receive_messages() == []


@patch("src.queue._get_sqs_client", return_value=None)
@patch("src.queue.settings")
def test_receive_messages_no_client(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "http://queue"
    from src.queue import receive_messages
    assert receive_messages() == []


# ---------------------------------------------------------------------------
# delete_message
# ---------------------------------------------------------------------------

@patch("src.queue._get_sqs_client")
@patch("src.queue.settings")
def test_delete_message_success(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "https://sqs.example.com/queue"
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    from src.queue import delete_message
    delete_message("rh_abc")

    mock_client.delete_message.assert_called_once_with(
        QueueUrl="https://sqs.example.com/queue",
        ReceiptHandle="rh_abc",
    )


@patch("src.queue._get_sqs_client", return_value=None)
@patch("src.queue.settings")
def test_delete_message_no_client(mock_settings, mock_get_client):
    mock_settings.SQS_QUEUE_URL = "http://queue"
    from src.queue import delete_message
    # Should not raise
    delete_message("rh_abc")
