"""OpenAlex retrieval connector for academic paper search.

Provides free API access to OpenAlex for retrieving academic papers,
with local caching to avoid repeated network calls.
"""

from dataclasses import dataclass, field
from typing import Any
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

from aat.retrieval.cache import RetrievalCache


@dataclass
class OpenAlexResult:
    """A single OpenAlex search result."""

    id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    language: str | None = None
    score: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "publication_year": self.publication_year,
            "doi": self.doi,
            "language": self.language,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpenAlexResult":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            authors=data.get("authors", []),
            abstract=data.get("abstract"),
            publication_year=data.get("publication_year"),
            doi=data.get("doi"),
            language=data.get("language"),
            score=data.get("score", 0.0),
        )


class OpenAlexClient:
    """Client for OpenAlex API with local caching.

    OpenAlex is a free, open index of scholarly papers. This client
    provides search functionality with local disk caching to avoid
    repeated network calls.

    Usage:
        client = OpenAlexClient(cache_dir=Path("./cache"))
        results = client.search("machine translation", max_results=10)
    """

    BASE_URL = "https://api.openalex.org/works"

    def __init__(
        self,
        cache_dir: Path,
        email: str | None = None,
        enable_web: bool = False,
    ) -> None:
        """
        Initialize the OpenAlex client.

        Args:
            cache_dir: Directory for cache storage.
            email: Optional email for OpenAlex polite pool (recommended).
            enable_web: Whether to enable web search. If False, all
                       searches return empty results without network calls.
        """
        self.cache = RetrievalCache(cache_dir / "openalex")
        self.email = email
        self.enable_web = enable_web

    def _make_request(self, url: str) -> dict | None:
        """Make HTTP request to OpenAlex API.

        Args:
            url: The URL to request.

        Returns:
            Parsed JSON response or None on error.
        """
        headers = {}
        if self.email:
            headers["User-Agent"] = f"mailto:{self.email}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None

    def search(
        self,
        query: str,
        max_results: int = 10,
        prefer_chinese: bool = True,
    ) -> list[OpenAlexResult]:
        """Search for academic papers.

        Args:
            query: The search query (title, keywords, etc.).
            max_results: Maximum number of results to return.
            prefer_chinese: Whether to prefer Chinese language results
                          (implemented by filtering after search).

        Returns:
            List of OpenAlexResult objects.
        """
        if not self.enable_web:
            # Web search disabled, return empty results
            return []

        # Check cache first
        cache_key = f"search:{query}:{max_results}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return [OpenAlexResult.from_dict(r) for r in cached]

        # Build search URL
        params = {
            "search": query,
            "per_page": min(max_results * 2, 25),  # Request more for filtering
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}?{query_string}"

        # Make request
        response = self._make_request(url)
        if response is None:
            return []

        # Parse results
        results = []
        for work in response.get("results", []):
            # Extract authors
            authors = []
            for authorship in work.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name", "")
                if name:
                    authors.append(name)

            # Determine language if available
            language = work.get("language")
            if not language and prefer_chinese:
                # Check title for Chinese characters
                title = work.get("display_name", "")
                if any("\u4e00" <= c <= "\u9fff" for c in title):
                    language = "zh"

            result = OpenAlexResult(
                id=work.get("id", ""),
                title=work.get("display_name", ""),
                authors=authors,
                abstract=work.get("abstract", ""),
                publication_year=work.get("publication_year"),
                doi=work.get("doi"),
                language=language,
                score=0.0,
            )
            results.append(result)

        # Prefer Chinese results if requested
        if prefer_chinese:
            zh_results = [r for r in results if r.language == "zh"]
            other_results = [r for r in results if r.language != "zh"]
            results = zh_results + other_results

        # Limit to max_results
        results = results[:max_results]

        # Cache results
        self.cache.set(cache_key, [r.to_dict() for r in results])

        return results

    def get_work_by_doi(self, doi: str) -> OpenAlexResult | None:
        """Retrieve a specific work by DOI.

        Args:
            doi: The DOI to look up.

        Returns:
            OpenAlexResult if found, None otherwise.
        """
        if not self.enable_web:
            return None

        # Normalize DOI
        if not doi.startswith("10."):
            doi = doi.replace("https://doi.org/", "")
            doi = doi.replace("http://doi.org/", "")

        # Check cache
        cache_key = f"doi:{doi}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return OpenAlexResult.from_dict(cached)

        # Make request
        url = f"{self.BASE_URL}/doi:{doi}"
        response = self._make_request(url)

        if response is None:
            return None

        # Parse result
        authors = []
        for authorship in response.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        result = OpenAlexResult(
            id=response.get("id", ""),
            title=response.get("display_name", ""),
            authors=authors,
            abstract=response.get("abstract", ""),
            publication_year=response.get("publication_year"),
            doi=response.get("doi"),
            language=response.get("language"),
            score=0.0,
        )

        # Cache result
        self.cache.set(cache_key, result.to_dict())

        return result
