from __future__ import annotations

from .sentiment import analyze_sentiment
from .topics_llm import extract_topics_llm
from .topics_nlp import extract_topics_nlp
from .triples import extract_triples
from .embeddings_client import compute_embeddings

__all__ = [
    "analyze_sentiment",
    "extract_topics_llm",
    "extract_topics_nlp",
    "extract_triples",
    "compute_embeddings",
]
