from __future__ import annotations

from ..config import Settings
from ..utils.logger import get_logger
from .llm_client import get_embeddings


def compute_embeddings(texts: list[str], cfg: Settings) -> list[list[float]] | None:
    """Compute embeddings for a list of texts.

    Returns list of embedding vectors, or None if embeddings are disabled
    or fail with fallback enabled.
    """
    logger = get_logger()

    if not cfg.EMBEDDINGS_ENABLE:
        logger.info("Embeddings disabled (EMBEDDINGS_ENABLE=False)")
        return None

    if not texts:
        return []

    batch_size = 100
    all_embeddings: list[list[float]] = []

    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = get_embeddings(cfg, batch)
            all_embeddings.extend(batch_embeddings)
            logger.info(
                "Embeddings batch %d/%d complete (%d texts)",
                i // batch_size + 1,
                (len(texts) + batch_size - 1) // batch_size,
                len(batch),
            )
        return all_embeddings
    except Exception as e:
        if cfg.EMBEDDINGS_FALLBACK_TO_SAMPLING:
            logger.warning(
                "Embeddings failed (%s), falling back to TF-IDF (EMBEDDINGS_FALLBACK_TO_SAMPLING=True)",
                e,
            )
            return None
        raise
