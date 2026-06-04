from __future__ import annotations

from typing import Any

from rag.seed_data import seed_travel_guides
from rag.setup import get_collection, get_embeddings


def _ensure_seeded() -> None:
    """Make the retriever self-healing so it still works before manual seeding."""
    collection = get_collection()
    if collection.count() == 0:
        seed_travel_guides(force=True)


def retrieve_travel_info(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Return the most relevant travel guide chunks for the given query."""
    _ensure_seeded()
    collection = get_collection()
    query_embedding = get_embeddings().embed_query(query)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    chunks: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] or {}
        chunks.append(
            {
                "content": document,
                "destination": metadata.get("destination", ""),
                "category": metadata.get("category", ""),
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return chunks

