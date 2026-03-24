"""Tests for src/orchestrator/llm_backends.py — LLM backend abstraction."""

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# generate — routing + fallback
# ---------------------------------------------------------------------------

@patch("src.orchestrator.llm_backends._generate_ollama", return_value="Hello from Ollama")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_ollama_primary(mock_settings, mock_ollama):
    mock_settings.LLM_BACKEND = "ollama"
    mock_settings.LLM_MAX_TOKENS = 512

    from src.orchestrator.llm_backends import generate
    result = generate("test prompt")
    assert result == "Hello from Ollama"
    mock_ollama.assert_called_once()


@patch("src.orchestrator.llm_backends._generate_huggingface", return_value="HF result")
@patch("src.orchestrator.llm_backends._generate_ollama", side_effect=Exception("down"))
@patch("src.orchestrator.llm_backends.settings")
def test_generate_fallback_to_huggingface(mock_settings, mock_ollama, mock_hf):
    mock_settings.LLM_BACKEND = "ollama"
    mock_settings.LLM_MAX_TOKENS = 512

    from src.orchestrator.llm_backends import generate
    result = generate("test prompt")
    assert result == "HF result"


@patch("src.orchestrator.llm_backends._generate_huggingface", side_effect=Exception("hf down"))
@patch("src.orchestrator.llm_backends._generate_ollama", side_effect=Exception("ollama down"))
@patch("src.orchestrator.llm_backends.settings")
def test_generate_all_backends_fail(mock_settings, mock_ollama, mock_hf):
    mock_settings.LLM_BACKEND = "ollama"
    mock_settings.LLM_MAX_TOKENS = 512

    from src.orchestrator.llm_backends import generate
    with pytest.raises(Exception):
        generate("test prompt")


@patch("src.orchestrator.llm_backends.settings")
def test_generate_unknown_backend(mock_settings):
    mock_settings.LLM_BACKEND = "unknown_backend"
    mock_settings.LLM_MAX_TOKENS = 512

    from src.orchestrator.llm_backends import generate
    with pytest.raises(ValueError, match="Unknown LLM_BACKEND"):
        generate("prompt")


@patch("src.orchestrator.llm_backends._generate_bedrock", return_value="Bedrock response")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_bedrock_primary(mock_settings, mock_bedrock):
    mock_settings.LLM_BACKEND = "bedrock"
    mock_settings.LLM_MAX_TOKENS = 256

    from src.orchestrator.llm_backends import generate
    result = generate("prompt", max_tokens=100)
    assert result == "Bedrock response"
    mock_bedrock.assert_called_once_with("prompt", 100)


@patch("src.orchestrator.llm_backends._generate_huggingface", return_value="HF direct")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_huggingface_primary(mock_settings, mock_hf):
    mock_settings.LLM_BACKEND = "huggingface"
    mock_settings.LLM_MAX_TOKENS = 256

    from src.orchestrator.llm_backends import generate
    result = generate("prompt")
    assert result == "HF direct"


# ---------------------------------------------------------------------------
# _generate_ollama
# ---------------------------------------------------------------------------

@patch("src.orchestrator.llm_backends.time.sleep")  # skip real backoff
@patch("src.orchestrator.llm_backends.requests.post")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_ollama_success(mock_settings, mock_post, mock_sleep):
    mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
    mock_settings.OLLAMA_MODEL = "llama3"

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Ollama says hi"}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    from src.orchestrator.llm_backends import _generate_ollama
    result = _generate_ollama("hello", 512)
    assert result == "Ollama says hi"


@patch("src.orchestrator.llm_backends.time.sleep")
@patch("src.orchestrator.llm_backends.requests.post")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_ollama_retries(mock_settings, mock_post, mock_sleep):
    mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
    mock_settings.OLLAMA_MODEL = "llama3"

    import requests
    mock_post.side_effect = [
        requests.RequestException("timeout"),
        requests.RequestException("timeout"),
        requests.RequestException("timeout"),  # MAX_RETRIES = 2, so 3 total attempts
    ]

    from src.orchestrator.llm_backends import _generate_ollama
    with pytest.raises(requests.RequestException):
        _generate_ollama("hello", 512)

    assert mock_post.call_count == 3  # 1 + 2 retries


# ---------------------------------------------------------------------------
# _generate_bedrock
# ---------------------------------------------------------------------------

@patch("src.orchestrator.llm_backends.settings")
def test_generate_bedrock_success(mock_settings):
    mock_settings.AWS_REGION = "us-east-1"
    mock_settings.BEDROCK_MODEL_ID = "amazon.nova-micro-v1:0"

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Bedrock says hello"}]}}
    }

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch("src.orchestrator.llm_backends.boto3", mock_boto3):
        from src.orchestrator.llm_backends import _generate_bedrock
        result = _generate_bedrock("test prompt", 256)

    assert result == "Bedrock says hello"


@patch("src.orchestrator.llm_backends.boto3", None)
@patch("src.orchestrator.llm_backends.settings")
def test_generate_bedrock_no_boto3(mock_settings):
    from src.orchestrator.llm_backends import _generate_bedrock
    with pytest.raises(RuntimeError, match="boto3 is required"):
        _generate_bedrock("prompt", 256)


# ---------------------------------------------------------------------------
# _generate_huggingface
# ---------------------------------------------------------------------------

@patch("src.orchestrator.llm_backends.time.sleep")
@patch("src.orchestrator.llm_backends.requests.post")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_huggingface_success(mock_settings, mock_post, mock_sleep):
    mock_settings.HF_MODEL_ID = "bigscience/bloom"
    mock_settings.HF_API_TOKEN = "hf_test_token"

    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"generated_text": "HF says hi"}]
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    from src.orchestrator.llm_backends import _generate_huggingface
    result = _generate_huggingface("hello", 100)
    assert result == "HF says hi"


@patch("src.orchestrator.llm_backends.time.sleep")
@patch("src.orchestrator.llm_backends.requests.post")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_huggingface_retries(mock_settings, mock_post, mock_sleep):
    mock_settings.HF_MODEL_ID = "bigscience/bloom"
    mock_settings.HF_API_TOKEN = "token"

    import requests
    mock_post.side_effect = [
        requests.RequestException("error"),
        requests.RequestException("error"),
        requests.RequestException("error"),
    ]

    from src.orchestrator.llm_backends import _generate_huggingface
    with pytest.raises(requests.RequestException):
        _generate_huggingface("hello", 100)

    assert mock_post.call_count == 3


# ---------------------------------------------------------------------------
# _generate_groq
# ---------------------------------------------------------------------------

@patch("src.orchestrator.llm_backends.time.sleep")
@patch("src.orchestrator.llm_backends.requests.post")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_groq_success(mock_settings, mock_post, mock_sleep):
    mock_settings.GROQ_API_KEY = "gsk_test"
    mock_settings.GROQ_MODEL_ID = "llama-3.1-8b-instant"

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "Groq says hi"}}]}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    from src.orchestrator.llm_backends import _generate_groq
    result = _generate_groq("hello", 256)
    assert result == "Groq says hi"


@patch("src.orchestrator.llm_backends.settings")
def test_generate_groq_no_api_key(mock_settings):
    mock_settings.GROQ_API_KEY = ""

    from src.orchestrator.llm_backends import _generate_groq
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is required"):
        _generate_groq("prompt", 256)


@patch("src.orchestrator.llm_backends._generate_groq", return_value="Groq response")
@patch("src.orchestrator.llm_backends.settings")
def test_generate_groq_primary(mock_settings, mock_groq):
    mock_settings.LLM_BACKEND = "groq"
    mock_settings.LLM_MAX_TOKENS = 256

    from src.orchestrator.llm_backends import generate
    result = generate("prompt")
    assert result == "Groq response"
    mock_groq.assert_called_once()
