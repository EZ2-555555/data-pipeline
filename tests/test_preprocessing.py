"""Tests for the preprocessing / chunking module."""

from src.preprocessing.chunker import normalize_text, chunk_text


def test_normalize_strips_html():
    raw = "<p>Hello <b>world</b></p>"
    assert normalize_text(raw) == "Hello world"


def test_normalize_collapses_whitespace():
    raw = "  too   many   spaces  "
    assert normalize_text(raw) == "too many spaces"


def test_normalize_unescapes_html_entities():
    raw = "AT&amp;T is a &lt;company&gt;"
    result = normalize_text(raw)
    assert "&" in result
    assert "<" not in result or "company" in result


def test_normalize_strips_code_blocks():
    raw = "Before ```python\nprint('hello')\n``` after"
    assert normalize_text(raw) == "Before after"


def test_normalize_strips_inline_code():
    raw = "Use `pip install` to install packages"
    assert normalize_text(raw) == "Use to install packages"


def test_normalize_strips_urls():
    raw = "Visit https://github.com/user/repo for details"
    assert normalize_text(raw) == "Visit for details"


def test_normalize_strips_markdown_images():
    raw = "See ![alt text](https://img.com/pic.png) here"
    assert normalize_text(raw) == "See here"


def test_normalize_strips_markdown_links():
    raw = "Read [the docs](https://docs.example.com) now"
    assert normalize_text(raw) == "Read now"


def test_normalize_strips_markdown_headings():
    raw = "## Section Title\nSome content"
    result = normalize_text(raw)
    assert "##" not in result
    assert "Section Title" in result


def test_normalize_strips_bold_italic():
    raw = "This is **bold** and *italic* text"
    assert normalize_text(raw) == "This is bold and italic text"


def test_normalize_strips_emojis():
    raw = "Great article 🔥🚀 about AI 🤖 trends"
    assert normalize_text(raw) == "Great article about AI trends"


def test_normalize_strips_control_chars():
    raw = "hidden\u200bzero\u200bwidth\ufeff spaces"
    assert normalize_text(raw) == "hiddenzerowidth spaces"


def test_normalize_strips_blockquotes():
    raw = "> This is quoted\n> Second line"
    result = normalize_text(raw)
    assert ">" not in result
    assert "This is quoted" in result
    assert "Second line" in result


def test_normalize_strips_html_comments():
    raw = "Before <!-- hidden comment --> after"
    assert normalize_text(raw) == "Before after"


def test_normalize_collapses_repeated_punctuation():
    raw = "Really important!!! Are you sure???"
    assert normalize_text(raw) == "Really important! Are you sure?"


def test_normalize_strips_strikethrough():
    raw = "This is ~~deleted~~ text"
    assert normalize_text(raw) == "This is deleted text"


def test_chunk_short_text_returns_single():
    text = "Short text that fits in one chunk."
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_splits_long_text():
    # Create text longer than chunk_size tokens
    text = " ".join(["word"] * 1200)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
