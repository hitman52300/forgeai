import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="forgeai_test_"))
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_DB_DIR"] = str(_TMP / "db")
os.environ["CHROMA_DIR"] = str(_TMP / "chroma")
os.environ["UPLOADS_DIR"] = str(_TMP / "uploads")
os.environ["ARTIFACTS_ROOT"] = str(_TMP / "artifacts")  # keep test runs out of the repo's artifacts/


@pytest.fixture
def tmp_root() -> Path:
    return _TMP


def make_pdf(pages: list[str]) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(heading: str, paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    import io
    import docx
    d = docx.Document()
    d.add_heading(heading, level=1)
    for p in paragraphs:
        d.add_paragraph(p)
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for i, row in enumerate(table):
            for j, v in enumerate(row):
                t.cell(i, j).text = v
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
