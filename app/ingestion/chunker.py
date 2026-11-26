"""Configurable chunking with metadata.  Prose is split recursively on separators;
tabular rows are grouped (never split mid-row) and keep their row references."""
from __future__ import annotations

from app.core.schemas import Chunk, RetrievalConfig
from app.ingestion.parser import ParsedDocument


def split_text(text: str, size: int, overlap: int, separators: list[str]) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    pieces = _recursive(text, size, separators)
    # merge small pieces into chunks of ~size with overlap
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + len(p) <= size:
            cur += p
        else:
            chunks.append(cur.strip())
            tail = cur[-overlap:] if overlap else ""
            # start the overlap at a word boundary
            if tail and " " in tail:
                tail = tail[tail.index(" ") + 1:]
            cur = tail + p
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if c]


def _recursive(text: str, size: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    for i, sep in enumerate(seps):
        if sep and sep in text:
            parts = text.split(sep)
            out: list[str] = []
            for j, part in enumerate(parts):
                piece = part + (sep if j < len(parts) - 1 else "")
                if len(piece) > size:
                    out.extend(_recursive(piece, size, seps[i + 1:]))
                elif piece:
                    out.append(piece)
            return out
    return [text[i:i + size] for i in range(0, len(text), size)]


def chunk_document(doc: ParsedDocument, document_id: str, content_hash: str, cfg: RetrievalConfig,
                   collection: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0

    def add(text: str, **meta) -> None:
        nonlocal idx
        cid = f"{content_hash[:12]}-{idx:04d}"
        chunks.append(Chunk(chunk_id=cid, document_id=document_id, source_filename=doc.filename, text=text,
                            chunk_index=idx, embedding_ref=f"{collection}/{cid}",
                            metadata={"file_type": doc.file_type, "content_hash": content_hash}, **meta))
        idx += 1

    row_segments = [s for s in doc.segments if s.kind == "table_rows" and s.row_start is not None]
    if row_segments:
        # group consecutive rows up to chunk_size characters; header columns stay in every row text
        group: list = []
        size = 0
        for s in row_segments:
            if group and size + len(s.text) > cfg.chunk_size:
                add("\n".join(g.text for g in group), row_start=group[0].row_start, row_end=group[-1].row_end,
                    content_type="table_rows")
                group, size = [], 0
            group.append(s)
            size += len(s.text) + 1
        if group:
            add("\n".join(g.text for g in group), row_start=group[0].row_start, row_end=group[-1].row_end,
                content_type="table_rows")

    for s in doc.segments:
        if s.kind == "table_rows" and s.row_start is not None:
            continue
        for piece in split_text(s.text, cfg.chunk_size, cfg.chunk_overlap, cfg.separators):
            prefix = f"[{doc.filename}{', ' + s.section if s.section else ''}] "
            add(prefix + piece, page=s.page, section=s.section,
                content_type="table_rows" if s.kind == "table_rows" else "prose")
    return chunks
