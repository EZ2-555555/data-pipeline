"""Tests for src/pipeline/run_pipeline.py — chunk/embed pipeline logic."""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# fetch_raw_documents
# ---------------------------------------------------------------------------

@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_fetch_raw_documents_returns_rows(mock_get_conn, mock_put_conn):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (1, "Title A", "Content A", "hn", "hash_a", None),
        (2, "Title B", "Content B", "arxiv", "hash_b", "2026-01-01"),
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.pipeline.run_pipeline import fetch_raw_documents
    docs = fetch_raw_documents()

    assert len(docs) == 2
    assert docs[0]["id"] == 1
    assert docs[0]["title"] == "Title A"
    assert docs[0]["published_at"] is None
    assert docs[1]["published_at"] == "2026-01-01"
    mock_put_conn.assert_called_once_with(mock_conn)


@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_fetch_raw_documents_empty(mock_get_conn, mock_put_conn):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.pipeline.run_pipeline import fetch_raw_documents
    docs = fetch_raw_documents()
    assert docs == []


# ---------------------------------------------------------------------------
# process_and_store
# ---------------------------------------------------------------------------

def test_process_and_store_empty_list():
    from src.pipeline.run_pipeline import process_and_store
    assert process_and_store([]) == 0


@patch("src.pipeline.run_pipeline.record_pipeline_chunks")
@patch("src.pipeline.run_pipeline.write_embeddings")
@patch("src.pipeline.run_pipeline.write_processed")
@patch("src.pipeline.run_pipeline.embed_texts")
@patch("src.pipeline.run_pipeline.chunk_text", return_value=["chunk1", "chunk2"])
@patch("src.pipeline.run_pipeline.normalize_text", return_value="normalized text")
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_process_and_store_happy_path(mock_get_conn, mock_put_conn,
                                       mock_normalize, mock_chunk,
                                       mock_embed, mock_write_proc,
                                       mock_write_emb, mock_record):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    mock_embed.return_value = [[0.1] * 384, [0.2] * 384]

    doc = {
        "id": 1, "title": "My Title", "content": "Hello world content here.",
        "source": "hn", "content_hash": "abc123", "published_at": "2026-01-01",
    }
    from src.pipeline.run_pipeline import process_and_store
    total = process_and_store([doc])

    assert total == 2
    mock_conn.commit.assert_called_once()
    mock_record.assert_called_once_with(2)
    mock_write_proc.assert_called_once()
    mock_write_emb.assert_called_once()


@patch("src.pipeline.run_pipeline.record_pipeline_chunks")
@patch("src.pipeline.run_pipeline.write_embeddings")
@patch("src.pipeline.run_pipeline.write_processed")
@patch("src.pipeline.run_pipeline.embed_texts")
@patch("src.pipeline.run_pipeline.chunk_text")
@patch("src.pipeline.run_pipeline.normalize_text", return_value="")
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_process_and_store_empty_content_marks_indexed(
    mock_get_conn, mock_put_conn, mock_normalize, mock_chunk,
    mock_embed, mock_write_proc, mock_write_emb, mock_record
):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    doc = {
        "id": 1, "title": "", "content": "",
        "source": "hn", "content_hash": "empty", "published_at": None,
    }
    from src.pipeline.run_pipeline import process_and_store
    total = process_and_store([doc])

    assert total == 0
    mock_embed.assert_not_called()


@patch("src.pipeline.run_pipeline.record_pipeline_error")
@patch("src.pipeline.run_pipeline.write_processed")
@patch("src.pipeline.run_pipeline.embed_texts", side_effect=RuntimeError("model error"))
@patch("src.pipeline.run_pipeline.chunk_text", return_value=["chunk1"])
@patch("src.pipeline.run_pipeline.normalize_text", return_value="some text")
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_process_and_store_embed_error_reverts_to_raw(mock_get_conn, mock_put_conn,
                                                       mock_normalize, mock_chunk,
                                                       mock_embed, mock_write_proc,
                                                       mock_record_err):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    doc = {
        "id": 1, "title": "Title", "content": "Some real content here.",
        "source": "arxiv", "content_hash": "xyz", "published_at": None,
    }
    from src.pipeline.run_pipeline import process_and_store
    total = process_and_store([doc])

    assert total == 0
    mock_record_err.assert_called_once_with("embed_texts")
    mock_conn.rollback.assert_not_called()
    mock_conn.commit.assert_called_once()
    executed_sqls = [str(c) for c in mock_cursor.execute.call_args_list]
    assert any("RAW" in sql for sql in executed_sqls)


@patch("src.pipeline.run_pipeline.record_pipeline_chunks")
@patch("src.pipeline.run_pipeline.write_embeddings")
@patch("src.pipeline.run_pipeline.write_processed")
@patch("src.pipeline.run_pipeline.embed_texts")
@patch("src.pipeline.run_pipeline.chunk_text", return_value=["chunk1"])
@patch("src.pipeline.run_pipeline.normalize_text", return_value="some text")
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_process_and_store_no_content_hash(mock_get_conn, mock_put_conn,
                                            mock_normalize, mock_chunk,
                                            mock_embed, mock_write_proc,
                                            mock_write_emb, mock_record):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    mock_embed.return_value = [[0.1] * 384]

    doc = {
        "id": 5, "title": "Title", "content": "Content here.",
        "source": "devto", "content_hash": "", "published_at": None,
    }
    from src.pipeline.run_pipeline import process_and_store
    total = process_and_store([doc])

    assert total == 1
    mock_write_proc.assert_not_called()
    mock_write_emb.assert_not_called()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@patch("src.pipeline.run_pipeline.process_and_store", return_value=5)
@patch("src.pipeline.run_pipeline.fetch_raw_documents", return_value=[{"id": 1}])
@patch("src.pipeline.run_pipeline.timed_metric")
def test_run_orchestrates(mock_timed, mock_fetch, mock_process):
    mock_timed.return_value.__enter__ = MagicMock()
    mock_timed.return_value.__exit__ = MagicMock(return_value=False)

    from src.pipeline.run_pipeline import run
    total = run()

    assert total == 5
    mock_fetch.assert_called_once()
    mock_process.assert_called_once_with([{"id": 1}])


# ---------------------------------------------------------------------------
# process_sqs_batch  (local imports: from src.queue import ...)
# ---------------------------------------------------------------------------

@patch("src.pipeline.run_pipeline.record_pipeline_error")
@patch("src.pipeline.run_pipeline.process_and_store", return_value=3)
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
@patch("src.queue.delete_message")
@patch("src.queue.receive_messages")
def test_process_sqs_batch_happy(mock_receive, mock_delete,
                                  mock_get_conn, mock_put_conn,
                                  mock_process, mock_err):
    mock_receive.return_value = [
        {"body": {"document_id": 1}, "receipt_handle": "rh1"},
    ]
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1, "T", "C", "hn", "h1", None)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.pipeline.run_pipeline import process_sqs_batch
    processed = process_sqs_batch()

    assert processed == 1
    mock_delete.assert_called_once_with("rh1")


@patch("src.queue.receive_messages", return_value=[])
def test_process_sqs_batch_no_messages(mock_receive):
    from src.pipeline.run_pipeline import process_sqs_batch
    processed = process_sqs_batch()
    assert processed == 0


@patch("src.queue.delete_message")
@patch("src.queue.receive_messages")
def test_process_sqs_batch_missing_doc_id(mock_receive, mock_delete):
    mock_receive.return_value = [
        {"body": {}, "receipt_handle": "rh1"},
    ]
    from src.pipeline.run_pipeline import process_sqs_batch
    processed = process_sqs_batch()
    assert processed == 0


@patch("src.queue.delete_message")
@patch("src.queue.receive_messages")
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
def test_process_sqs_batch_already_processed(mock_get_conn, mock_put_conn,
                                              mock_receive, mock_delete):
    """Document not found in RAW state => delete message, don't process."""
    mock_receive.return_value = [
        {"body": {"document_id": 99}, "receipt_handle": "rh2"},
    ]
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.pipeline.run_pipeline import process_sqs_batch
    processed = process_sqs_batch()
    assert processed == 0
    mock_delete.assert_called_once_with("rh2")


# ---------------------------------------------------------------------------
# lambda_handler  (local imports: init_schema, ingesters, settings)
# ---------------------------------------------------------------------------

@patch("src.pipeline.run_pipeline.run", return_value=10)
@patch("src.config.settings")
@patch("src.db.init_schema.init_schema")
@patch("src.ingestion.rss_ingester.run", return_value=1)
@patch("src.ingestion.github_ingester.run", return_value=4)
@patch("src.ingestion.devto_ingester.run", return_value=2)
@patch("src.ingestion.arxiv_ingester.run", return_value=3)
@patch("src.ingestion.hn_ingester.run", return_value=5)
def test_lambda_handler_calls_ingesters(mock_hn, mock_arxiv, mock_devto,
                                         mock_gh, mock_rss, mock_init,
                                         mock_settings, mock_run):
    mock_settings.SQS_ENABLED = False

    from src.pipeline.run_pipeline import lambda_handler
    result = lambda_handler({}, {})

    mock_init.assert_called_once()
    assert result["ingested"]["hn"] == 5
    assert result["chunks_created"] == 10


@patch("src.pipeline.run_pipeline.run", return_value=0)
@patch("src.config.settings")
@patch("src.db.init_schema.init_schema")
@patch("src.ingestion.rss_ingester.run", return_value=0)
@patch("src.ingestion.github_ingester.run", return_value=0)
@patch("src.ingestion.devto_ingester.run", return_value=0)
@patch("src.ingestion.arxiv_ingester.run", return_value=0)
@patch("src.ingestion.hn_ingester.run", return_value=0)
def test_lambda_handler_sqs_enabled_skips_pipeline(mock_hn, mock_arxiv, mock_devto,
                                                     mock_gh, mock_rss, mock_init,
                                                     mock_settings, mock_run):
    mock_settings.SQS_ENABLED = True

    from src.pipeline.run_pipeline import lambda_handler
    result = lambda_handler({}, {})

    mock_run.assert_not_called()
    assert result["chunks_created"] == 0


@patch("src.pipeline.run_pipeline.run", return_value=10)
@patch("src.config.settings")
@patch("src.db.init_schema.init_schema")
@patch("src.ingestion.rss_ingester.run", return_value=1)
@patch("src.ingestion.github_ingester.run", return_value=4)
@patch("src.ingestion.devto_ingester.run", return_value=2)
@patch("src.ingestion.arxiv_ingester.run", return_value=3)
@patch("src.ingestion.hn_ingester.run", side_effect=Exception("fail"))
def test_lambda_handler_ingester_failure(mock_hn, mock_arxiv, mock_devto,
                                          mock_gh, mock_rss, mock_init,
                                          mock_settings, mock_run):
    mock_settings.SQS_ENABLED = False

    from src.pipeline.run_pipeline import lambda_handler
    result = lambda_handler({}, {})

    assert result["ingested"]["hn"] == -1


# ---------------------------------------------------------------------------
# preprocess_handler  (local imports: init_schema, json)
# ---------------------------------------------------------------------------

@patch("src.pipeline.run_pipeline.record_pipeline_error")
@patch("src.pipeline.run_pipeline.process_and_store", return_value=1)
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
@patch("src.db.init_schema.init_schema")
def test_preprocess_handler_with_records(mock_init, mock_get_conn, mock_put_conn,
                                          mock_process, mock_err):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (10, "T", "C", "hn", "h1", None)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    event = {
        "Records": [
            {"messageId": "m1", "body": '{"document_id": 10}'},
        ]
    }
    from src.pipeline.run_pipeline import preprocess_handler
    result = preprocess_handler(event, {})

    assert result["batchItemFailures"] == []


@patch("src.pipeline.run_pipeline.process_sqs_batch", return_value=3)
@patch("src.db.init_schema.init_schema")
def test_preprocess_handler_no_records_fallback(mock_init, mock_batch):
    event = {}
    from src.pipeline.run_pipeline import preprocess_handler
    result = preprocess_handler(event, {})
    assert result["processed"] == 3


@patch("src.pipeline.run_pipeline.record_pipeline_error")
@patch("src.pipeline.run_pipeline.process_and_store", side_effect=RuntimeError("fail"))
@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
@patch("src.db.init_schema.init_schema")
def test_preprocess_handler_failure_returns_batch_failures(
    mock_init, mock_get_conn, mock_put_conn, mock_process, mock_err
):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (10, "T", "C", "hn", "h1", None)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    event = {
        "Records": [
            {"messageId": "m1", "body": '{"document_id": 10}'},
        ]
    }
    from src.pipeline.run_pipeline import preprocess_handler
    result = preprocess_handler(event, {})

    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "m1"


@patch("src.pipeline.run_pipeline.put_connection")
@patch("src.pipeline.run_pipeline.get_connection")
@patch("src.db.init_schema.init_schema")
def test_preprocess_handler_missing_row(mock_init, mock_get_conn, mock_put_conn):
    """Record references a doc that doesn't exist / already processed."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    event = {
        "Records": [
            {"messageId": "m2", "body": '{"document_id": 999}'},
        ]
    }
    from src.pipeline.run_pipeline import preprocess_handler
    result = preprocess_handler(event, {})

    assert result["batchItemFailures"] == []
