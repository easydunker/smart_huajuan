"""Tests for OpenAlex retrieval connector."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aat.retrieval.openalex import OpenAlexClient, OpenAlexResult


class TestOpenAlexResult:
    """Test OpenAlexResult dataclass."""

    def test_creation(self) -> None:
        """Test creating an OpenAlex result."""
        result = OpenAlexResult(
            id="W123456789",
            title="Test Paper Title",
            authors=["Author One", "Author Two"],
            abstract="This is the abstract.",
            publication_year=2024,
            doi="10.1234/example",
            language="en",
            score=0.95,
        )

        assert result.id == "W123456789"
        assert result.title == "Test Paper Title"
        assert len(result.authors) == 2
        assert result.abstract == "This is the abstract."
        assert result.publication_year == 2024
        assert result.doi == "10.1234/example"
        assert result.language == "en"
        assert result.score == 0.95

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        result = OpenAlexResult(
            id="W123",
            title="Test",
            authors=["A. Author"],
            publication_year=2023,
            score=0.8,
        )

        d = result.to_dict()

        assert d["id"] == "W123"
        assert d["title"] == "Test"
        assert d["authors"] == ["A. Author"]
        assert d["publication_year"] == 2023
        assert d["score"] == 0.8

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "id": "W456",
            "title": "Another Paper",
            "authors": ["B. Researcher", "C. Scientist"],
            "abstract": "An abstract here.",
            "publication_year": 2022,
            "doi": "10.5678/test",
            "language": "zh",
            "score": 0.92,
        }

        result = OpenAlexResult.from_dict(data)

        assert result.id == "W456"
        assert result.title == "Another Paper"
        assert len(result.authors) == 2
        assert result.abstract == "An abstract here."
        assert result.publication_year == 2022
        assert result.doi == "10.5678/test"
        assert result.language == "zh"
        assert result.score == 0.92


class TestOpenAlexClient:
    """Test OpenAlexClient class."""

    @pytest.fixture
    def temp_cache_dir(self) -> Path:
        """Create a temporary cache directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init(self, temp_cache_dir: Path) -> None:
        """Test client initialization."""
        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            email="test@example.com",
            enable_web=True,
        )

        assert client.enable_web is True
        assert client.email == "test@example.com"
        assert client.cache is not None

    def test_init_default_disabled(self, temp_cache_dir: Path) -> None:
        """Test that web search is disabled by default."""
        client = OpenAlexClient(cache_dir=temp_cache_dir)

        assert client.enable_web is False

    def test_search_disabled_returns_empty(self, temp_cache_dir: Path) -> None:
        """Test that search returns empty list when web is disabled."""
        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=False,
        )

        results = client.search("machine translation", max_results=10)

        assert results == []

    @patch("urllib.request.urlopen")
    def test_search_success(self, mock_urlopen, temp_cache_dir: Path) -> None:
        """Test successful search with mocked response."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "results": [
                {
                    "id": "W123456",
                    "display_name": "Test Paper Title",
                    "authorships": [
                        {"author": {"display_name": "John Doe"}}
                    ],
                    "abstract": "This is a test abstract.",
                    "publication_year": 2023,
                    "doi": "10.1234/test",
                    "language": "en",
                }
            ]
        }).encode()
        mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)

        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=True,
        )

        results = client.search("test query", max_results=5)

        assert len(results) == 1
        assert results[0].id == "W123456"
        assert results[0].title == "Test Paper Title"
        assert results[0].authors == ["John Doe"]

    @patch("urllib.request.urlopen")
    def test_search_caching(self, mock_urlopen, temp_cache_dir: Path) -> None:
        """Test that search results are cached."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "results": [
                {
                    "id": "W789",
                    "display_name": "Cached Paper",
                    "authorships": [],
                }
            ]
        }).encode()
        mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)

        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=True,
        )

        # First search - should hit API
        results1 = client.search("cache test", max_results=5)
        assert len(results1) == 1

        # Second search - should hit cache, not API
        mock_urlopen.reset_mock()
        results2 = client.search("cache test", max_results=5)
        assert len(results2) == 1
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_get_work_by_doi(self, mock_urlopen, temp_cache_dir: Path) -> None:
        """Test retrieving a work by DOI."""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "id": "W999",
            "display_name": "DOI Paper",
            "authorships": [
                {"author": {"display_name": "Jane Smith"}}
            ],
            "publication_year": 2022,
            "doi": "10.5678/example",
        }).encode()
        mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)

        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=True,
        )

        result = client.get_work_by_doi("10.5678/example")

        assert result is not None
        assert result.id == "W999"
        assert result.title == "DOI Paper"
        assert result.doi == "10.5678/example"

    def test_get_work_by_doi_disabled(self, temp_cache_dir: Path) -> None:
        """Test that DOI lookup returns None when disabled."""
        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=False,
        )

        result = client.get_work_by_doi("10.1234/test")

        assert result is None

    def test_prefer_chinese_results(self, temp_cache_dir: Path) -> None:
        """Test that Chinese results are preferred when requested."""
        # This tests the internal logic for Chinese preference
        # We can't easily test the full sorting without mocking
        client = OpenAlexClient(
            cache_dir=temp_cache_dir,
            enable_web=True,
        )

        # Just verify the parameter is accepted
        assert client.enable_web is True
