import pytest

from app.core.schemas import RetrievalConfig
from app.ingestion.chunker import chunk_document, split_text
from app.ingestion.loader import IngestionError, safe_filename, validate_file
from app.ingestion.parser import parse
from tests.conftest import make_docx, make_pdf


def test_rejects_bad_extension_and_size():
    with pytest.raises(IngestionError, match="unsupported"):
        validate_file("evil.exe", b"MZ...")
    with pytest.raises(IngestionError, match="empty"):
        validate_file("a.txt", b"")
    with pytest.raises(IngestionError, match="PDF"):
        validate_file("fake.pdf", b"hello")
    with pytest.raises(IngestionError, match="limit"):
        validate_file("big.txt", b"a" * (21 * 1024 * 1024))


def test_safe_filename_strips_paths():
    assert safe_filename("../../etc/passwd.txt") == "passwd.txt"
    assert safe_filename("C:\\x\\my file?.pdf") in ("my file_.pdf", "x_my file_.pdf")


def test_pdf_pages_and_sections():
    data = make_pdf(["1. Introduction\nThis manual covers widgets.", "2. Returns\nReturns accepted within 30 days."])
    doc = parse(validate_file("m.pdf", data))
    assert doc.page_count == 2
    pages = {s.page for s in doc.segments}
    assert pages == {1, 2}
    assert any("30 days" in s.text and s.page == 2 for s in doc.segments)


def test_docx_with_table():
    data = make_docx("Policy", ["Rule one applies to all."], [["Item", "Limit"], ["Pens", "5"]])
    doc = parse(validate_file("p.docx", data))
    assert any("Item: Pens; Limit: 5" in s.text for s in doc.segments)


def test_csv_preserves_columns_and_rows():
    data = b"id,name,price\nA1,Bolt,2.50\nA2,Nut,0.40\n"
    doc = parse(validate_file("c.csv", data))
    assert doc.columns == ["id", "name", "price"] and doc.row_count == 2
    chunks = chunk_document(doc, "d1", "h" * 64, RetrievalConfig(), "col")
    assert chunks[0].row_start == 2 and chunks[0].row_end == 3
    assert "name: Bolt" in chunks[0].text and chunks[0].content_type == "table_rows"


def test_split_text_overlap_and_size():
    text = " ".join(f"word{i}" for i in range(600))
    parts = split_text(text, 300, 60, ["\n\n", "\n", ". ", " "])
    assert all(len(p) <= 300 for p in parts)
    assert len(parts) > 5
    # overlap: end of one chunk re-appears at the start of the next
    assert parts[0].split()[-1] in parts[1]


def test_chunk_ids_deterministic():
    doc = parse(validate_file("a.txt", b"Alpha section.\n\nBeta section with more words."))
    c1 = chunk_document(doc, "d", "abc123" * 10, RetrievalConfig(), "col")
    c2 = chunk_document(doc, "d", "abc123" * 10, RetrievalConfig(), "col")
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]
    assert all(c.embedding_ref.startswith("col/") for c in c1)
