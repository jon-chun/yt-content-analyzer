from __future__ import annotations


class YTCAError(Exception):
    """Base exception for yt-content-analyzer."""


class ConfigError(YTCAError):
    """Invalid or inconsistent configuration."""


class PreflightError(YTCAError):
    """Preflight checks failed."""

    def __init__(self, results: list[dict]) -> None:
        self.results = results
        failed = [r for r in results if not r.get("OK")]
        names = ", ".join(r.get("NAME", "?") for r in failed) or "unknown"
        super().__init__(f"Preflight failed: {names}")


class CollectionError(YTCAError):
    """Error during comment/transcript collection."""


class EnrichmentError(YTCAError):
    """Error during enrichment pipeline."""
