from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import chromadb
from langchain_community.embeddings import HuggingFaceEmbeddings

from utils.config import settings


# Persist the vector store inside the backend so the seed data survives restarts.
CHROMA_DIR = Path(settings.rag_chroma_dir)
COLLECTION_NAME = "travel_guides"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the local sentence-transformer once and reuse it."""
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    """Return the persistent Chroma client."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    """Get or create the shared travel guide collection."""
    return get_chroma_client().get_or_create_collection(name=COLLECTION_NAME)
