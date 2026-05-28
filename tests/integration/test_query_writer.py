"""Integration tests for the query_writer module.

Tests the ``query_chunks`` async function with all external dependencies
(LightRAG, OpenRouter AP) mocked.  No real API keys or network calls.

Coverage:
  - Normal chunk retrieval with structured JSON parsing
  - Graceful LightRAG initialisation failure
  - Long-content truncation (>800 characters)
  - Fallback to a single chunk when LightRAG returns empty results
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Add src/ to sys.path so that pipeline modules can be imported.
# (conftest.py also does this, but we keep it here for standalone running.)
_src = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from query_writer import query_chunks


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_query_chunks_returns_chunk_list(mock_lightrag):
    """``query_chunks`` returns a list of dicts with the expected keys.

    Each result dict must contain ``chunk_index`` (1-based int), ``ref_id``
    (str), and ``content`` (str).  The LightRAG response is wrapped in a
    markdown JSON code block to exercise the real parsing path.
    """
    mock_lightrag.aquery = AsyncMock(
        return_value=(
            "```json\n"
            '{"reference_id": "1", "content": "Machine learning is a subset of AI"}\n'
            '{"reference_id": "2", "content": "Deep learning uses neural networks"}\n'
            '{"reference_id": "3", "content": "Model interpretability remains a challenge"}\n'
            "```"
        ),
    )
    mock_config = {"rag": mock_lightrag}

    with patch("config.initialize_lightrag", AsyncMock(return_value=mock_config)):
        result = await query_chunks("machine learning", top_k=3)

    assert isinstance(result, list)
    assert len(result) == 3, f"Expected 3 chunks, got {len(result)}"

    for i, chunk in enumerate(result, 1):
        assert "chunk_index" in chunk, f"Chunk {i} missing 'chunk_index'"
        assert "ref_id" in chunk, f"Chunk {i} missing 'ref_id'"
        assert "content" in chunk, f"Chunk {i} missing 'content'"
        assert isinstance(chunk["chunk_index"], int)
        assert isinstance(chunk["ref_id"], str)
        assert isinstance(chunk["content"], str)

    assert result[0]["chunk_index"] == 1
    assert result[1]["chunk_index"] == 2
    assert result[2]["chunk_index"] == 3

    assert result[0]["ref_id"] == "1"
    assert result[1]["ref_id"] == "2"
    assert result[2]["ref_id"] == "3"


# ---------------------------------------------------------------------------
# Failure: LightRAG init
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_query_chunks_handles_lightrag_failure():
    """Graceful handling when ``initialize_lightrag`` raises an exception.

    Instead of crashing, ``query_chunks`` must return a single error dict
    with ``ref_id`` set to ``"error"`` and a human-readable message that
    includes the original exception text.
    """
    with patch(
        "config.initialize_lightrag",
        AsyncMock(side_effect=RuntimeError("API connection failed")),
    ):
        result = await query_chunks("test query", top_k=5)

    assert isinstance(result, list)
    assert len(result) == 1, (
        f"Expected single error dict, got {len(result)} chunks"
    )

    assert result[0]["ref_id"] == "error"
    assert "Failed to initialize LightRAG" in result[0]["content"]
    assert "API connection failed" in result[0]["content"]


# ---------------------------------------------------------------------------
# Content truncation
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_query_chunks_truncates_long_content(mock_lightrag):
    """Content longer than 800 characters is truncated to 800 chars + ``...``.

    The mock LightRAG response contains a single chunk whose content is
    1000 characters long.  After truncation the returned content should be
    exactly 803 characters (800 + 3 for the ellipsis) and end with ``...``.
    """
    long_content = "A" * 1000
    mock_lightrag.aquery = AsyncMock(
        return_value=(
            "```json\n"
            f'{{"reference_id": "1", "content": "{long_content}"}}\n'
            "```"
        ),
    )
    mock_config = {"rag": mock_lightrag}

    with patch("config.initialize_lightrag", AsyncMock(return_value=mock_config)):
        result = await query_chunks("long content test", top_k=1)

    assert len(result) == 1, f"Expected 1 chunk, got {len(result)}"

    content = result[0]["content"]
    assert len(content) == 803, (
        f"Expected 803 chars (800 truncated + 3 for '...'), "
        f"got {len(content)}"
    )
    assert content.endswith("..."), "Truncated content must end with '...'"
    assert content == "A" * 800 + "..."


# ---------------------------------------------------------------------------
# Empty results fallback
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_query_chunks_returns_minimum_one_chunk(mock_lightrag):
    """Always returns at least one chunk when LightRAG returns empty results.

    When the LightRAG response is empty (or contains no parseable JSON),
    ``query_chunks`` must return a single fallback chunk with ``chunk_index=1``,
    ``ref_id="1"``, and fallback content ``"No content retrieved"``.
    """
    mock_lightrag.aquery = AsyncMock(return_value="")
    mock_config = {"rag": mock_lightrag}

    with patch("config.initialize_lightrag", AsyncMock(return_value=mock_config)):
        result = await query_chunks("empty result test", top_k=5)

    assert isinstance(result, list)
    assert len(result) == 1, (
        f"Expected at least 1 fallback chunk, got {len(result)}"
    )

    assert result[0]["chunk_index"] == 1
    assert result[0]["ref_id"] == "1"
    assert result[0]["content"] == "No content retrieved"
