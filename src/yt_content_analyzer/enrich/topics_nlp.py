from __future__ import annotations

import logging

from ..config import Settings

logger = logging.getLogger(__name__)


def extract_topics_nlp(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
    embeddings: list[list[float]] | None = None,
) -> list[dict]:
    """Extract topics using NLP methods (TF-IDF + NMF or KMeans with embeddings).

    Args:
        items: List of comment/chunk dicts with a "TEXT" key.
        video_id: The YouTube video ID.
        asset_type: "comments" or "transcripts".
        cfg: Settings instance.
        embeddings: Optional pre-computed embedding vectors (one per item).

    Returns:
        List of topic dicts with keys:
        VIDEO_ID, ASSET_TYPE, TOPIC_ID, LABEL, KEYWORDS, REPRESENTATIVE_TEXTS, SCORE
    """
    if not items:
        return []

    texts = [item.get("TEXT", "") for item in items]
    texts = [t for t in texts if t.strip()]
    if not texts:
        return []

    n_topics = min(10, len(texts) // 20 + 1)
    n_topics = max(1, n_topics)

    if embeddings is not None and len(embeddings) == len(texts):
        return _topics_via_kmeans(texts, embeddings, video_id, asset_type, n_topics, logger)
    else:
        return _topics_via_nmf(texts, video_id, asset_type, n_topics, logger)


def _topics_via_kmeans(
    texts: list[str],
    embeddings: list[list[float]],
    video_id: str,
    asset_type: str,
    n_topics: int,
    logger,
) -> list[dict]:
    """Cluster embeddings with KMeans, extract keywords per cluster via TF-IDF."""
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    logger.info("Topics via KMeans clustering (%d clusters, %d texts)", n_topics, len(texts))

    X = np.array(embeddings)
    km = KMeans(n_clusters=n_topics, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english")
    tfidf = vectorizer.fit_transform(texts)
    feature_names = vectorizer.get_feature_names_out()

    results: list[dict] = []
    for topic_id in range(n_topics):
        mask = labels == topic_id
        cluster_indices = np.where(mask)[0]
        if len(cluster_indices) == 0:
            continue

        # Get top keywords by averaging TF-IDF scores in cluster
        cluster_tfidf = tfidf[cluster_indices].toarray().mean(axis=0)
        top_keyword_indices = cluster_tfidf.argsort()[-10:][::-1]
        keywords = [feature_names[i] for i in top_keyword_indices if cluster_tfidf[i] > 0]

        # Representative texts (closest to centroid)
        centroid = km.cluster_centers_[topic_id]
        distances = np.linalg.norm(X[cluster_indices] - centroid, axis=1)
        rep_indices = distances.argsort()[:3]
        rep_texts = [texts[cluster_indices[i]][:200] for i in rep_indices]

        label = ", ".join(keywords[:3]) if keywords else f"Topic {topic_id}"
        score = round(float(len(cluster_indices)) / len(texts), 4)

        results.append({
            "VIDEO_ID": video_id,
            "ASSET_TYPE": asset_type,
            "TOPIC_ID": topic_id,
            "LABEL": label,
            "KEYWORDS": keywords[:10],
            "REPRESENTATIVE_TEXTS": rep_texts,
            "SCORE": score,
        })

    return results


def _topics_via_nmf(
    texts: list[str],
    video_id: str,
    asset_type: str,
    n_topics: int,
    logger,
) -> list[dict]:
    """Extract topics via TF-IDF + NMF (Non-negative Matrix Factorization)."""
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    logger.info("Topics via TF-IDF + NMF (%d topics, %d texts)", n_topics, len(texts))

    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english")
    tfidf = vectorizer.fit_transform(texts)
    feature_names = vectorizer.get_feature_names_out()

    nmf = NMF(n_components=n_topics, random_state=42, max_iter=300)
    W = nmf.fit_transform(tfidf)  # doc-topic matrix
    H = nmf.components_            # topic-term matrix

    results: list[dict] = []
    for topic_id in range(n_topics):
        top_indices = H[topic_id].argsort()[-10:][::-1]
        keywords = [feature_names[i] for i in top_indices if H[topic_id][i] > 0]

        # Representative texts: highest weight for this topic
        doc_scores = W[:, topic_id]
        rep_doc_indices = doc_scores.argsort()[-3:][::-1]
        rep_texts = [texts[i][:200] for i in rep_doc_indices if doc_scores[i] > 0]

        label = ", ".join(keywords[:3]) if keywords else f"Topic {topic_id}"
        score = round(float(doc_scores.sum()) / max(W.sum(), 1e-10), 4)

        results.append({
            "VIDEO_ID": video_id,
            "ASSET_TYPE": asset_type,
            "TOPIC_ID": topic_id,
            "LABEL": label,
            "KEYWORDS": keywords[:10],
            "REPRESENTATIVE_TEXTS": rep_texts,
            "SCORE": score,
        })

    return results
