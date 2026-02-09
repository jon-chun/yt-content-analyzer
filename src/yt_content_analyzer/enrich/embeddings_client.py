from __future__ import annotations

import logging
import time

from ..config import Settings
from .llm_client import get_embeddings

logger = logging.getLogger(__name__)


def compute_embeddings(texts: list[str], cfg: Settings) -> list[list[float]] | None:
    """Compute embeddings for a list of texts.

    Returns list of embedding vectors, or None if embeddings are disabled
    or fail with fallback enabled.
    """

    if not cfg.EMBEDDINGS_ENABLE:
        logger.info("Embeddings disabled (EMBEDDINGS_ENABLE=False)")
        return None

    if not texts:
        return []

    batch_size = 100
    max_retries = cfg.EMBEDDINGS_MAX_RETRIES
    backoff_base = cfg.BACKOFF_BASE_SECONDS
    all_embeddings: list[list[float]] = []

    try:
        total_batches = (len(texts) + batch_size - 1) // batch_size
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_num = i // batch_size + 1

            for attempt in range(max_retries):
                try:
                    batch_embeddings = get_embeddings(cfg, batch)
                    all_embeddings.extend(batch_embeddings)
                    break
                except Exception:
                    if attempt == max_retries - 1:
                        raise
                    wait = backoff_base * (2 ** attempt)
                    logger.warning(
                        "Embeddings batch %d/%d attempt %d failed, retrying in %.1fs",
                        batch_num, total_batches, attempt + 1, wait,
                    )
                    time.sleep(wait)

            logger.info(
                "Embeddings batch %d/%d complete (%d texts)",
                batch_num, total_batches, len(batch),
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
