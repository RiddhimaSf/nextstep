"""
Retrieval: search_kb queries the Chroma collection built by ingest.py,
using dense (embedding similarity) search with optional metadata filters.

Deliberately dense-only, no hybrid/BM25 — see Day 1 and Day 4 reasoning:
the corpus is small (~50 chunks) and well-defined, so hybrid search
solves a scale problem this project doesn't have.
"""

import chromadb

# Score threshold (tau) below which retrieval is considered insufficient.
# Chroma returns a distance (lower = more similar) by default; this
# threshold is expressed as a similarity score derived from that distance
# so it reads intuitively (higher = better), matching the SLO language
# already used elsewhere in this project's spec.
SCORE_THRESHOLD = 0.3


def _distance_to_score(distance: float) -> float:
    """Converts Chroma's distance metric to a 0-1 similarity score
    (higher = more relevant), for consistency with how thresholds are
    described in the rest of the spec."""
    return max(0.0, 1.0 - distance)


def search_kb(query: str, k: int = 6, filters: dict | None = None) -> list[dict]:
    """
    Returns a list of dicts: {id, text, score, source, title, citation}

    filters example: {"borough": "Brooklyn"} or {"category": "financial"}
    Only chunks matching ALL given filter key/value pairs are considered.
    """
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(
        name="nextstep_kb",
        metadata={"hnsw:space": "cosine"},
    )
    print(f"DEBUG: collection has {collection.count()} items")


    where_clause = None
    if filters:
        where_clause = {key: value for key, value in filters.items()}

    results = collection.query(
        query_texts=[query],
        n_results=k,
        where=where_clause,
    )

    output = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]

    for chunk_id, text, distance, meta in zip(ids, documents, distances, metadatas):
        score = _distance_to_score(distance)
        output.append({
            "id": chunk_id,
            "text": text,
            "score": round(score, 4),
            "source": meta["source"],
            "title": meta["title"],
            "citation": f"{meta['source']}#{chunk_id}",
        })

    return output


def best_score_below_threshold(results: list[dict]) -> bool:
    """Code-enforced check (not left to model judgment) for whether
    retrieval quality is too low to answer from — the deterministic half
    of the INSUFFICIENT_CONTEXT rule, per Day 4 design decision."""
    if not results:
        return True
    return results[0]["score"] < SCORE_THRESHOLD


if __name__ == "__main__":
    # Quick manual check — run after ingest.py to confirm retrieval works
    # before wiring this into the agent as a tool.
    test_query = "Does Bellevue have a SANE nurse?"
    results = search_kb(test_query, k=3)
    print(f"Query: {test_query}\n")
    for r in results:
        print(f"[{r['citation']}] score={r['score']} — {r['text'][:80]}...")
    print(f"\nBest score below threshold ({SCORE_THRESHOLD})? {best_score_below_threshold(results)}")