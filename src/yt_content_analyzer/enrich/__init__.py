from __future__ import annotations

# Lazy imports — enrichment modules depend on optional extras (numpy, pandas,
# scikit-learn, textblob).  Importing eagerly causes ImportError when the
# 'nlp' extras group is not installed.

__all__ = [
    "analyze_sentiment",
    "extract_topics_llm",
    "extract_topics_nlp",
    "extract_triples",
    "compute_embeddings",
    "extract_urls",
    "summarize_content",
]

_LAZY_IMPORTS = {
    "analyze_sentiment": ".sentiment",
    "extract_topics_llm": ".topics_llm",
    "extract_topics_nlp": ".topics_nlp",
    "extract_triples": ".triples",
    "compute_embeddings": ".embeddings_client",
    "extract_urls": ".url_extraction",
    "summarize_content": ".summarization",
}


def __getattr__(name: str):
    module_path = _LAZY_IMPORTS.get(name)
    if module_path is not None:
        import importlib
        mod = importlib.import_module(module_path, __package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
