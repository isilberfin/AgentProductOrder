import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from config import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX, PINECONE_CLOUD, PINECONE_REGION
from constants import EMBED_MODEL, DIMENSION, NS_PRODUCTS, NS_PROCEDURES
from worker.r2 import fetch_bytes

_openai = OpenAI(api_key=OPENAI_API_KEY)
_pc     = Pinecone(api_key=PINECONE_API_KEY)


def _get_index():
    existing = [i["name"] for i in _pc.list_indexes()]
    if PINECONE_INDEX not in existing:
        print(f"Creating Pinecone index '{PINECONE_INDEX}'...")
        _pc.create_index(
            name=PINECONE_INDEX,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
    return _pc.Index(PINECONE_INDEX)


def _embed(texts: list[str]) -> list[list[float]]:
    response = _openai.embeddings.create(input=texts, model=EMBED_MODEL)
    return [r.embedding for r in response.data]


def _content_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _needs_reindex(index, namespace: str, current_hash: str) -> bool:
    try:
        result = index.fetch(ids=[f"_hash_{namespace}"], namespace=namespace)
        stored = result.vectors.get(f"_hash_{namespace}", {})
        return stored.get("metadata", {}).get("hash") != current_hash
    except Exception:
        return True


def _save_hash(index, namespace: str, current_hash: str):
    sentinel = [1.0] + [0.0] * (DIMENSION - 1)
    index.upsert(
        vectors=[{"id": f"_hash_{namespace}", "values": sentinel,
                  "metadata": {"hash": current_hash}}],
        namespace=namespace,
    )


def _chunk_text(text: str, min_chunk: int = 120) -> list[str]:
    """Split by double newline, merging chunks that are too short."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        current = (current + "\n\n" + para).strip() if current else para
        if len(current) >= min_chunk:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _index_text(index, filename: str, namespace: str, min_chunk: int = 120):
    raw = fetch_bytes(filename)
    current_hash = _content_hash(raw)
    if not _needs_reindex(index, namespace, current_hash):
        return

    print(f"Re-indexing '{filename}' -> [{namespace}]...")
    chunks = _chunk_text(raw.decode("utf-8"), min_chunk=min_chunk)

    try:
        index.delete(delete_all=True, namespace=namespace)
    except Exception:
        pass

    embeddings = _embed(chunks)
    vectors = [
        {
            "id": f"{namespace}-{i}",
            "values": embeddings[i],
            "metadata": {"text": chunks[i]},
        }
        for i in range(len(chunks))
    ]
    index.upsert(vectors=vectors, namespace=namespace)
    _save_hash(index, namespace, current_hash)
    print(f"✅  Indexed {len(vectors)} chunks into Pinecone [{namespace}]")


_index = _get_index()
_index_text(_index, "products.txt",          NS_PRODUCTS,   min_chunk=120)
_index_text(_index, "order_procedures.txt",  NS_PROCEDURES, min_chunk=0)


def retrieve(query: str, n: int = 3) -> list[str]:
    q_embedding = _embed([query])[0]
    results = _index.query(vector=q_embedding, top_k=n, include_metadata=True,
                           namespace=NS_PRODUCTS)
    return [m["metadata"]["text"] for m in results["matches"]]


def retrieve_order(query: str, n: int = 3) -> list[str]:
    q_embedding = _embed([query])[0]
    results = _index.query(vector=q_embedding, top_k=n, include_metadata=True,
                           namespace=NS_PROCEDURES)
    return [m["metadata"]["text"] for m in results["matches"]]
