"""Text / structure extraction for TXT, PDF, DOCX and CSV."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from app.ingestion.loader import IngestionError, ValidatedFile


@dataclass
class Segment:
    text: str
    page: int | None = None
    section: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    kind: str = "prose"  # prose | table_rows


@dataclass
class ParsedDocument:
    filename: str
    file_type: str
    segments: list[Segment]
    page_count: int | None = None
    row_count: int | None = None
    columns: list[str] | None = None
    table: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def full_text(self) -> str:
        return "\n\n".join(s.text for s in self.segments)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


_HEADING = re.compile(r"^\s*((\d+(\.\d+)*\.?)\s+[A-Z][^\n]{2,80}|[A-Z][A-Z &/\-]{3,60})\s*$")


def _sections(text: str) -> list[tuple[str | None, str]]:
    """Split prose into (heading, body) pairs using simple, generic heading heuristics."""
    out: list[tuple[str | None, str]] = []
    current, buf = None, []
    for line in text.splitlines():
        if _HEADING.match(line) and len(line.split()) <= 12:
            if buf and "".join(buf).strip():
                out.append((current, "\n".join(buf).strip()))
            current, buf = line.strip(), [line]
        else:
            buf.append(line)
    if buf and "\n".join(buf).strip():
        out.append((current, "\n".join(buf).strip()))
    return out


def parse_txt(f: ValidatedFile) -> ParsedDocument:
    text = _decode(f.data)
    segs = [Segment(text=b, section=h) for h, b in _sections(text)]
    return ParsedDocument(f.filename, "txt", segs)


def parse_pdf(f: ValidatedFile) -> ParsedDocument:
    import pymupdf
    try:
        doc = pymupdf.open(stream=f.data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise IngestionError(f"'{f.filename}' could not be opened as PDF: {e}") from e
    if doc.needs_pass:
        raise IngestionError(f"'{f.filename}' is password-protected")
    segs: list[Segment] = []
    last_section = None
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        for h, body in _sections(text):
            last_section = h or last_section
            segs.append(Segment(text=body, page=i, section=last_section))
    n = doc.page_count
    doc.close()
    if not any(s.text.strip() for s in segs):
        raise IngestionError(f"'{f.filename}' has no extractable text (scanned PDF? OCR is not supported)")
    return ParsedDocument(f.filename, "pdf", segs, page_count=n)


def parse_docx(f: ValidatedFile) -> ParsedDocument:
    import docx
    try:
        d = docx.Document(io.BytesIO(f.data))
    except Exception as e:  # noqa: BLE001
        raise IngestionError(f"'{f.filename}' could not be opened as DOCX: {e}") from e
    segs: list[Segment] = []
    section, buf = None, []
    for p in d.paragraphs:
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style.startswith("heading") and p.text.strip():
            if buf:
                segs.append(Segment(text="\n".join(buf), section=section))
            section, buf = p.text.strip(), [p.text.strip()]
        elif p.text.strip():
            buf.append(p.text)
    if buf:
        segs.append(Segment(text="\n".join(buf), section=section))
    for t_idx, table in enumerate(d.tables, start=1):
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        if not rows:
            continue
        header, body = rows[0], rows[1:]
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, r)) for r in body]
        segs.append(Segment(text=f"Table {t_idx}\n" + "\n".join(lines), section=f"Table {t_idx}", kind="table_rows"))
    if not segs:
        raise IngestionError(f"'{f.filename}' contains no text")
    return ParsedDocument(f.filename, "docx", segs)


def parse_csv(f: ValidatedFile) -> ParsedDocument:
    try:
        df = pd.read_csv(io.StringIO(_decode(f.data)), dtype=str, keep_default_na=False)
    except Exception as e:  # noqa: BLE001
        raise IngestionError(f"'{f.filename}' is not a valid CSV: {e}") from e
    if df.empty or len(df.columns) == 0:
        raise IngestionError(f"'{f.filename}' has no rows")
    df.columns = [str(c).strip() for c in df.columns]
    segs = []
    for i, row in df.iterrows():
        row_no = int(i) + 2  # +1 header, +1 to make it 1-based like a spreadsheet
        text = f"[{f.filename} row {row_no}] " + "; ".join(f"{c}: {row[c]}" for c in df.columns)
        segs.append(Segment(text=text, row_start=row_no, row_end=row_no, kind="table_rows"))
    return ParsedDocument(f.filename, "csv", segs, row_count=len(df), columns=list(df.columns), table=df)


PARSERS = {".txt": parse_txt, ".pdf": parse_pdf, ".docx": parse_docx, ".csv": parse_csv}


def parse(f: ValidatedFile) -> ParsedDocument:
    try:
        return PARSERS[f.extension](f)
    except IngestionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise IngestionError(f"'{f.filename}' could not be parsed: {e}") from e
