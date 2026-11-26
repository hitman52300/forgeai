"""Real embeddings + real ChromaDB (no LLM)."""
from app.core.schemas import RetrievalConfig
from app.database.repositories import Repository
from app.database.supabase_client import LocalBackend
from app.ingestion.pipeline import KnowledgeBase
from app.ingestion.vector_store import VectorStore
from tests.conftest import make_pdf


def test_ingest_retrieve_dedup_and_versioning(tmp_path):
    repo = Repository(LocalBackend(tmp_path / "db"))
    kb = KnowledgeBase("proj-kb-1", repo)
    cfg = RetrievalConfig(chunk_size=400, chunk_overlap=50, top_k=3)
    pdf = make_pdf(["Returns\nCustomers may return items within 30 days with a receipt.",
                    "Shipping\nStandard shipping takes 5 business days."])
    csv = b"sku,name,stock\nS1,Blue mug,12\nS2,Red mug,0\n"
    rep = kb.ingest([("policy.pdf", pdf), ("stock.csv", csv), ("copy.pdf", pdf), ("bad.exe", b"x")], cfg)
    assert {d.filename for d in rep.documents} == {"policy.pdf", "stock.csv"}
    assert rep.duplicates and rep.errors

    store = VectorStore(rep.collection)
    hits = store.query("How long do I have to return an item?", 3)
    assert hits[0].chunk.source_filename == "policy.pdf" and hits[0].chunk.page == 1
    assert hits[0].score > 0.3
    hits = store.query("red mug stock level", 3)
    assert any(h.chunk.source_filename == "stock.csv" for h in hits)

    # modify one file -> version 2, old chunks replaced
    pdf2 = make_pdf(["Returns\nCustomers may return items within 14 days with a receipt."])
    rep2 = kb.ingest([("policy.pdf", pdf2), ("stock.csv", csv)], cfg, sync_removed=True)
    changes = {c["filename"]: c["change_type"] for c in rep2.changes}
    assert changes == {"policy.pdf": "modified", "stock.csv": "unchanged"}
    texts = " ".join(c.text for c in store.all_chunks({"source_filename": "policy.pdf"}))
    assert "14 days" in texts and "30 days" not in texts
    docs = repo.list_documents("proj-kb-1")
    pol = [d for d in docs if d["filename"] == "policy.pdf"][0]
    assert pol["current_version"] == 2
    assert [v["change_type"] for v in repo.document_versions(pol["id"])] == ["added", "modified"]

    # re-index under a different chunking config
    col = kb.ensure_index(RetrievalConfig(chunk_size=200, chunk_overlap=20))
    assert VectorStore(col).count() > 0
