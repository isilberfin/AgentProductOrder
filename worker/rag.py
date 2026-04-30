import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from config import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX, PINECONE_CLOUD, PINECONE_REGION

PRODUCTS_PATH   = Path(__file__).parent.parent / "data" / "products.json"
PROCEDURES_PATH = Path(__file__).parent.parent / "data" / "order_procedures.json"
EMBED_MODEL = "text-embedding-3-small"
DIMENSION   = 1536

NS_PRODUCTS   = "products"
NS_PROCEDURES = "order-procedures"

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


def _index_products(index):
    stats = index.describe_index_stats()
    ns_stats = stats.get("namespaces", {}).get(NS_PRODUCTS, {})
    if ns_stats.get("vector_count", 0) > 0:
        return

    products = json.loads(PRODUCTS_PATH.read_text())
    docs, ids = [], []
    for p in products:
        colors = p.get("colors", {})
        color_text = (
            f"Available colors: {', '.join(colors.get('available', []))}. "
            f"Limited edition: {', '.join(colors.get('limited_edition', []))}. "
            f"{colors.get('note', '')}"
        ) if colors else ""
        doc = (
            f"{p['name']}. {p['description']} "
            f"{color_text} "
            f"Specs: {p['specs']}. "
            f"Warranty: {p['warranty']}. "
            f"Return policy: {p['return_policy']}. "
            f"{p['faq']}"
        )
        docs.append(doc)
        ids.append(p["id"])

    embeddings = _embed(docs)
    vectors = [
        {"id": ids[i], "values": embeddings[i], "metadata": {"text": docs[i]}}
        for i in range(len(docs))
    ]
    index.upsert(vectors=vectors, namespace=NS_PRODUCTS)
    print(f"✅  Indexed {len(vectors)} products into Pinecone [{NS_PRODUCTS}]")


def _index_procedures(index):
    stats = index.describe_index_stats()
    ns_stats = stats.get("namespaces", {}).get(NS_PROCEDURES, {})
    if ns_stats.get("vector_count", 0) > 0:
        return

    procedures = json.loads(PROCEDURES_PATH.read_text())
    docs, ids = [], []
    for p in procedures:
        doc = f"Q: {p['question']} A: {p['answer']}"
        docs.append(doc)
        ids.append(p["id"])

    embeddings = _embed(docs)
    vectors = [
        {"id": ids[i], "values": embeddings[i], "metadata": {"text": docs[i]}}
        for i in range(len(docs))
    ]
    index.upsert(vectors=vectors, namespace=NS_PROCEDURES)
    print(f"✅  Indexed {len(vectors)} procedures into Pinecone [{NS_PROCEDURES}]")


_index = _get_index()
_index_products(_index)
_index_procedures(_index)


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
