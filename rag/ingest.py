"""
Ingest pipeline: converts NextStep's existing real content (currently
hardcoded in crisis.py) into Chunk objects, embeds them, and stores them
in a local Chroma vector database.

No document splitting/chunking-by-size is used here, deliberately — see
Day 4 reasoning: our real content (hospital entries, org entries, legal
topics) is already naturally short and self-contained, so the "split a
long document into overlapping windows" approach from generic RAG
tutorials doesn't apply. Each real-world entry becomes exactly one chunk.
"""

from pydantic import BaseModel
import chromadb


class Chunk(BaseModel):
    id: str
    text: str
    source: str
    title: str
    section: str | None = None
    updated_at: str | None = None
    borough: str | None = None
    category: str | None = None


def _slugify(name: str) -> str:
    """Turn a human name into a safe, stable chunk id."""
    return (
        name.lower()
        .replace(" ", "_")
        .replace("'", "")
        .replace("–", "-")
        .replace(",", "")
    )


def hospitals_to_chunks(hospitals: list[dict]) -> list[Chunk]:
    chunks = []
    for h in hospitals:
        text = (
            f"{h['name']} in {h['borough']} has a SANE-certified nurse "
            f"available 24/7 for sexual assault survivors. "
            f"Address: {h['address']}. Phone: {h['phone']}."
        )
        chunks.append(Chunk(
            id=_slugify(h["name"]),
            text=text,
            source="hospital_directory",
            title=h["name"],
            borough=h["borough"],
        ))
    return chunks


def safe_places_to_chunks(safe_places: dict) -> list[Chunk]:
    chunks = []
    for borough, orgs in safe_places.items():
        for org in orgs:
            text = (
                f"{org['name']} in {borough} is a {org['type']}, "
                f"available {org['hours']}. "
                f"Address: {org['address']}. Phone: {org['phone']}."
            )
            chunks.append(Chunk(
                id=_slugify(org["name"]),
                text=text,
                source="safe_places",
                title=org["name"],
                borough=borough,
                category=org["type"],
            ))
    return chunks


def legal_and_financial_chunks() -> list[Chunk]:
    """
    Hand-written chunks for content that lives as inline card() text in
    crisis.py rather than in a structured dict — legal process info,
    financial assistance info, mental health resources. Written as
    natural-language chunks matching the same pattern as the hospital
    and safe-places chunks, sourced from the real text already in the app.
    """
    return [
        Chunk(
            id="reporting_is_your_choice",
            text=(
                "Reporting to police is entirely a survivor's choice in New York City. "
                "You do not have to report to receive medical care or have forensic "
                "evidence collected. There is no deadline to decide whether to report."
            ),
            source="legal_resources",
            title="Reporting is your choice",
            category="legal",
        ),
        Chunk(
            id="evidence_kit_retention",
            text=(
                "If a forensic exam was done and the survivor chose not to report, "
                "the evidence kit is stored securely for 20 years under New York law. "
                "The survivor can decide to report at any point during that time, and "
                "the evidence will still be available. Evidence can be collected up to "
                "5 days after the assault."
            ),
            source="legal_resources",
            title="Evidence kit retention",
            category="legal",
        ),
        Chunk(
            id="how_to_report",
            text=(
                "To report a sexual assault in New York City, contact the NYPD Special "
                "Victims Division at 646-610-7273, or the NYS Police Sexual Assault "
                "Hotline at 1-844-845-7269. Survivors have the right to have a trained "
                "advocate present for any part of this process, free of charge, arranged "
                "through Safe Horizon at 1-800-621-4673."
            ),
            source="legal_resources",
            title="How to report",
            category="legal",
        ),
        Chunk(
            id="protective_order",
            text=(
                "A protective order legally requires an abuser or perpetrator to stay "
                "away from the survivor. It can be applied for even without reporting to "
                "the police. Safe Horizon provides free help with this at 1-800-621-4673 "
                "or safehorizon.org."
            ),
            source="legal_resources",
            title="Protective order",
            category="legal",
        ),
        Chunk(
            id="forensic_exam_is_free",
            text=(
                "The forensic (SANE) exam is completely free under federal law in New "
                "York City. Survivors cannot be billed for it, no insurance is needed, "
                "and there is no cost regardless of which certified hospital performs it."
            ),
            source="financial_resources",
            title="Forensic exam is free",
            category="financial",
        ),
        Chunk(
            id="ovs_compensation",
            text=(
                "New York's Office of Victim Services (OVS) can reimburse crime-related "
                "costs including medical bills, counselling, and lost wages. As of a "
                "December 2025 rule change, a police report is not always required — a "
                "Crime Verification Form signed by a medical or mental health provider "
                "can be used instead for most types of compensation. Apply at "
                "ovs.ny.gov or call 1-800-247-8035."
            ),
            source="financial_resources",
            title="OVS victim compensation",
            category="financial",
        ),
        Chunk(
            id="crime_victims_treatment_center",
            text=(
                "The Crime Victims Treatment Center will file an OVS compensation claim "
                "on a survivor's behalf and work to secure the maximum reimbursement. "
                "Call 212-523-4728."
            ),
            source="financial_resources",
            title="Crime Victims Treatment Center filing assistance",
            category="financial",
        ),
        Chunk(
            id="sanctuary_for_families",
            text=(
                "Sanctuary for Families helps with compensation claims alongside legal "
                "support for survivors. Visit sanctuaryforfamilies.org."
            ),
            source="financial_resources",
            title="Sanctuary for Families",
            category="financial",
        ),
        Chunk(
            id="safe_horizon_counseling",
            text=(
                "Safe Horizon offers free individual and group counselling for survivors "
                "in New York City, no insurance needed. Call 1-800-621-4673 or visit "
                "safehorizon.org."
            ),
            source="mental_health_resources",
            title="Safe Horizon counselling",
            category="mental_health",
        ),
        Chunk(
            id="rainn_local_support_finder",
            text=(
                "RAINN's local support finder helps survivors find trauma-informed "
                "therapists and support groups near them, at centers.rainn.org."
            ),
            source="mental_health_resources",
            title="RAINN local support finder",
            category="mental_health",
        ),
        Chunk(
            id="nyc988",
            text=(
                "NYC 988 provides free mental health support by call or text, available "
                "24/7, at nyc988.cityofnewyork.us."
            ),
            source="mental_health_resources",
            title="NYC 988",
            category="mental_health",
        ),
    ]


def filter_collision_test_chunks() -> list[Chunk]:
    """
    Chunks specifically designed to stress filter combinations, not just
    single-dimension filtering. Added after feedback correctly pointed out
    that the original smoke set (one Brooklyn query) only proved
    single-filter correctness, not that borough+category resolve ties
    correctly when multiple chunks share a filter value but differ on
    the actual fact being asked about.

    Two collision types:
    1. Same borough, different SANE-certification status — tests whether
       a borough filter alone is enough, or whether the retriever/model
       can still distinguish between two same-borough hospitals correctly
       on the actual content, not just the filter match.
    2. Cross-category chunks that both mention "compensation" — tests
       whether category filtering (financial vs. legal) actually
       disambiguates two chunks that share vocabulary, rather than the
       system relying on category alone without checking content still
       matches the real question.
    """
    return [
        # Collision type 1: same borough (Manhattan), different SANE status
        Chunk(
            id="test_manhattan_hospital_no_sane",
            text=(
                "Test General Hospital in Manhattan is a general emergency "
                "room but does NOT currently have SANE-certified nursing "
                "staff. Survivors should be directed to a SANE-certified "
                "hospital instead. Address: 100 Test Street, New York, NY. "
                "Phone: (212) 555-0100."
            ),
            source="hospital_directory",
            title="Test General Hospital (filter-collision test entry)",
            borough="Manhattan",
        ),
        # Collision type 2: "compensation" appears in both a legal and a
        # financial chunk, testing whether category filtering correctly
        # disambiguates rather than the model just grabbing whichever
        # chunk mentions the keyword first.
        Chunk(
            id="legal_compensation_via_civil_suit",
            text=(
                "Separate from OVS victim compensation, a survivor may "
                "also pursue compensation directly from a perpetrator "
                "through a civil lawsuit. This is a legal process distinct "
                "from the OVS government compensation program and "
                "typically requires a private attorney; Sanctuary for "
                "Families and Legal Aid organizations can advise on "
                "whether this route is appropriate for a specific case."
            ),
            source="legal_resources",
            title="Compensation via civil suit (legal route)",
            category="legal",
        ),
    ]


def build_corpus(hospitals: list[dict], safe_places: dict, include_test_chunks: bool = False) -> list[Chunk]:
    """Combine all sources into one corpus. Call this with the real
    HOSPITALS and SAFE_PLACES data imported from crisis.py.

    include_test_chunks: when True, adds the filter-collision test chunks
    (see filter_collision_test_chunks docstring) — used for smoke testing
    filter behavior, NOT intended to remain in the production corpus.
    Defaults to False so a normal ingest run never accidentally includes
    test data.
    """
    chunks = (
        hospitals_to_chunks(hospitals)
        + safe_places_to_chunks(safe_places)
        + legal_and_financial_chunks()
    )
    if include_test_chunks:
        chunks += filter_collision_test_chunks()
    return chunks


def embed_and_upsert(chunks: list[Chunk], collection_name: str = "nextstep_kb") -> int:
    """
    Embeds each chunk's text and stores it in a local Chroma collection,
    along with its metadata. Chroma's default embedding function runs
    locally (no external API call needed) — appropriate for this corpus
    size, consistent with the "don't over-build past what the problem
    needs" principle applied throughout this sprint.
    """
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c.id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "source": c.source,
            "title": c.title,
            "section": c.section or "",
            "updated_at": c.updated_at or "",
            "borough": c.borough or "",
            "category": c.category or "",
        }
        for c in chunks
    ]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from crisis import HOSPITALS, SAFE_PLACES

    include_tests = "--with-test-chunks" in sys.argv
    corpus = build_corpus(HOSPITALS, SAFE_PLACES, include_test_chunks=include_tests)
    count = embed_and_upsert(corpus)
    print(f"Ingested {count} chunks into the nextstep_kb collection.")
    print(f"Sources: {sorted(set(c.source for c in corpus))}")
    if include_tests:
        print("NOTE: filter-collision test chunks were included. Run again "
              "without --with-test-chunks to rebuild the clean production corpus.")