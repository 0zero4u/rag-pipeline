"""Shared test fixtures for the RAG pipeline test suite.

Provides reusable fixtures for unit, integration, and e2e tests.
All file-based fixtures use tmp_path for temporary file creation.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module path setup: add src/ to sys.path so all tests can import directly
# without duplicating this logic in every test file.
# ---------------------------------------------------------------------------
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ===========================================================================
# Data fixtures
# ===========================================================================


@pytest.fixture
def sample_parsed_pdf():
    """Return a ParsedPDF instance with standard test data.

    Provides a ParsedPDF object with:
    - filename = ``test_paper.pdf``
    - content = ``test content about machine learning``
    - Fully populated PDFMetadata including title, authors, year, doi,
      abstract, and two references.

    The object is returned as a ParsedPDF dataclass instance (not a raw
    dict) so that both ``isinstance(parsed, dict)`` and attribute-access
    code paths can be exercised by consumers such as
    ``citation_map.build_citation_map()``.
    """
    from parser import ParsedPDF, PDFMetadata

    metadata = PDFMetadata(
        title="Test Paper on Machine Learning",
        authors=["Alice Researcher", "Bob Scholar"],
        year="2023",
        doi="10.1234/test.ml.2023",
        abstract="This paper explores machine learning approaches for data analysis.",
        references=[
            {"authors": ["Smith"], "title": "Foundations of ML", "year": "2021"},
            {"authors": ["Jones"], "title": "Deep Learning Survey", "year": "2022"},
        ],
        source="llm",
        confidence="high",
    )

    return ParsedPDF(
        filename="test_paper.pdf",
        content="test content about machine learning",
        metadata=metadata,
        first_page_snippet="test content about machine learning",
        start_snippet="test content about machine learning",
        end_snippet="References\nSmith (2021)\nJones (2022)",
        page_count=5,
        has_tables=False,
        has_formulas=False,
    )


@pytest.fixture
def sample_citation_map():
    """Return a CitationMap with one citation entry.

    Builds a full CitationMap object containing a single entry for
    ``test_paper.pdf`` with sample authors, year, DOI, and reference
    keys.  Also pre-populates the ``author_index`` and ``year_index``
    convenience dictionaries so that index lookups work out of the box.
    """
    from citation_map import CitationEntry, CitationMap

    entry = CitationEntry(
        filename="test_paper.pdf",
        title="Test Paper on Machine Learning",
        authors=["Alice Researcher", "Bob Scholar"],
        year="2023",
        doi="10.1234/test.ml.2023",
        reference_keys=["Researcher-2023"],
    )

    return CitationMap(
        citations={"test_paper.pdf": entry},
        author_index={
            "Alice Researcher": ["test_paper.pdf"],
            "Bob Scholar": ["test_paper.pdf"],
        },
        year_index={"2023": ["test_paper.pdf"]},
    )


@pytest.fixture
def sample_prose_with_citations():
    """Return prose containing ``[CHUNK-N]`` citation markers.

    Returns a string with ``[CHUNK-1]``, ``[CHUNK-3]``, and ``[CHUNK-5]``
    markers embedded in academic prose.  Useful for testing citation
    validation, extraction, and formatting logic in the auditor and
    write-agent toolchain.
    """
    return (
        "Machine learning has transformed modern data analysis [CHUNK-1]. "
        "Deep neural networks, in particular, have shown remarkable performance "
        "across a wide range of tasks [CHUNK-3]. "
        "However, challenges remain in model interpretability and generalization "
        "to out-of-distribution samples [CHUNK-5]."
    )


@pytest.fixture
def sample_prose_no_citations():
    """Return plain prose without any ``[CHUNK-N]`` markers.

    Provides clean academic text containing no citation markers at all.
    Intended for testing edge cases such as empty validation results,
    gap detection with no references, or prose that should pass
    citation checks trivially.
    """
    return (
        "Machine learning has transformed modern data analysis. "
        "Deep neural networks, in particular, have shown remarkable performance. "
        "However, challenges remain in model interpretability and generalization."
    )


# ===========================================================================
# Temporary-file fixtures (use tmp_path)
# ===========================================================================


@pytest.fixture
def sample_citation_map_json(tmp_path):
    """Create a temporary ``citation_map.json`` and return its path.

    Writes a JSON file whose structure matches ``asdict(CitationMap)``,
    containing one citation entry for ``test_paper.pdf`` plus
    ``author_index`` and ``year_index`` lookup tables.

    Returns:
        str: Absolute path to the temporary file.
    """
    data = {
        "citations": {
            "test_paper.pdf": {
                "filename": "test_paper.pdf",
                "title": "Test Paper on Machine Learning",
                "authors": ["Alice Researcher", "Bob Scholar"],
                "year": "2023",
                "doi": "10.1234/test.ml.2023",
                "reference_keys": ["Researcher-2023"],
            }
        },
        "author_index": {
            "Alice Researcher": ["test_paper.pdf"],
            "Bob Scholar": ["test_paper.pdf"],
        },
        "year_index": {
            "2023": ["test_paper.pdf"],
        },
    }

    file_path = tmp_path / "citation_map.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return str(file_path)


@pytest.fixture
def sample_doc_status(tmp_path):
    """Create a temporary ``kv_store_doc_status.json`` and return its path.

    Writes a JSON file mimicking LightRAG's document-status KV store,
    with ``created_at`` timestamps and ``file_path`` entries.  Documents
    are sorted by ``created_at`` in the real code to map 1-based chunk
    indices to filenames for citation validation.

    Returns:
        str: Absolute path to the temporary file.
    """
    data = {
        "doc_001": {
            "created_at": "2024-01-15T10:00:00",
            "file_path": "test_paper.pdf",
            "content_summary": "Machine learning research paper",
            "status": "processed",
        },
        "doc_002": {
            "created_at": "2024-01-15T10:01:00",
            "file_path": "another_paper.pdf",
            "content_summary": "Deep learning survey",
            "status": "processed",
        },
    }

    file_path = tmp_path / "kv_store_doc_status.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return str(file_path)


# ===========================================================================
# Mock fixtures
# ===========================================================================


@pytest.fixture
def mock_lightrag():
    """Return a ``MockLightRAG`` instance with a fake ``aquery()``.

    The returned instance provides:
    - ``working_dir`` attribute (set to a temp-like path).
    - ``async aquery(query, param=None)`` that returns a JSON string
      with ``reference_id`` and ``content`` fields, simulating
      LightRAG's naive-mode query output.

    The default response contains three sample chunks about machine
    learning.  Tests can override ``instance.aquery`` or subclass
    ``MockLightRAG`` to return custom payloads.
    """

    class MockLightRAG:
        """Simulates LightRAG's query interface for testing.

        Attributes:
            working_dir: Filesystem path LightRAG would use for KV
                storage (mocked here to a placeholder).
        """

        def __init__(self, working_dir: str = "/tmp/mock_lightrag_working_dir"):
            self.working_dir = working_dir

        async def aquery(self, query: str, param: Any = None) -> str:
            """Return a JSON string representing LightRAG chunk results.

            Args:
                query: The search query string (ignored in mock).
                param: Optional ``QueryParam`` object (ignored).

            Returns:
                JSON array string where each object has ``reference_id``
                and ``content`` keys.
            """
            chunks = [
                {
                    "reference_id": "1",
                    "content": (
                        "Machine learning is a subset of artificial intelligence "
                        "that focuses on building systems that learn from data."
                    ),
                },
                {
                    "reference_id": "2",
                    "content": (
                        "Deep learning uses neural networks with multiple layers "
                        "to progressively extract higher-level features from raw input."
                    ),
                },
                {
                    "reference_id": "3",
                    "content": (
                        "Model interpretability remains a key challenge in deploying "
                        "machine learning systems in production environments."
                    ),
                },
            ]
            return json.dumps(chunks, indent=2)

    return MockLightRAG()


@pytest.fixture
def mock_llm_func():
    """Return an async callable that simulates an LLM returning JSON metadata.

    The returned function accepts the same signature as
    ``config.create_llm_func()`` output:

    .. code-block:: python

        await llm_func(prompt, system_prompt=None, history_messages=[], **kwargs)

    It always returns a JSON string containing ``title``, ``authors``,
    ``year``, ``abstract``, and ``references`` keys, regardless of the
    input.  Tests that need custom responses can replace this fixture
    with a function that inspects the ``prompt`` argument.
    """

    async def _mock_llm(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list | None = None,
        **kwargs: Any,
    ) -> str:
        """Mock LLM returning fixed metadata JSON.

        Args:
            prompt: The user prompt (ignored in mock).
            system_prompt: Optional system instructions (ignored).
            history_messages: Optional chat history (ignored).

        Returns:
            JSON string with ``title``, ``authors``, ``year``,
            ``abstract``, and ``references``.
        """
        metadata = {
            "title": "Test Paper on Machine Learning",
            "authors": ["Alice Researcher", "Bob Scholar"],
            "year": "2023",
            "abstract": (
                "This paper explores machine learning approaches "
                "for data analysis."
            ),
            "references": [
                "Smith, J. (2021). Foundations of Machine Learning.",
                "Jones, K. (2022). Deep Learning: A Comprehensive Survey.",
            ],
        }
        return json.dumps(metadata)

    return _mock_llm
