"""ChromaDB wrapper: one collection per project knowledge base (cosine space)."""
from __future__ import annotations

import json
from functools import lru_cache

import chromadb

from app.config import get_settings
from app.core.schemas import Chunk, RetrievedChunk
from app.ingestion.embeddings import get_embedder


@lru_cache
def get_client() -> chromadb.ClientAPI:
    """CHROMA_MODE=local: persistent ChromaDB on disk (default).
    CHROMA_MODE=cloud: hosted Chroma Cloud (CHROMA_TENANT, CHROMA_DATABASE, CHROMA_API_KEY), so a stateless
    backend container keeps its vectors across restarts."""
    s = get_settings()
    if s.chroma_mode == "cloud":
        if not (s.chroma_api_key and s.chroma_tenant and s.chroma_database):
            raise RuntimeError("CHROMA_MODE=cloud needs CHROMA_TENANT, CHROMA_DATABASE and CHROMA_API_KEY in .env")
        return chromadb.CloudClient(tenant=s.chroma_tenant, database=s.chroma_database, api_key=s.chroma_api_key)
    path = s.path(s.chroma_dir)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=chromadb.Settings(anonymized_telemetry=False))


def collection_name(project_id: str, chunk_size: int, chunk_overlap: int) -> str:
    # separate index per chunking configuration so the optimizer can re-chunk without destroying the old index
    return f"p_{project_id.replace('-', '')[:24]}_c{chunk_size}_o{chunk_overlap}"


class VectorStore:
    def __init__(self, name: str):
        self.name = name
        self.col = get_client().get_or_create_collection(name, metadata={"hnsw:space": "cosine"})

    # -------------------------------------------------------------- write
    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vecs = get_embedder().embed([c.text for c in chunks])
        self.col.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=vecs,
            documents=[c.text for c in chunks],
            metadatas=[_meta(c) for c in chunks],
        )
        return len(chunks)

    def delete_document(self, document_id: str) -> None:
        self.col.delete(where={"document_id": document_id})

    def delete_hash(self, content_hash: str) -> None:
        self.col.delete(where={"content_hash": content_hash})

    # -------------------------------------------------------------- read
    def count(self) -> int:
        return self.col.count()

    def query(self, text: str, top_k: int, where: dict | None = None) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        vec = get_embedder().embed([text])[0]
        res = self.col.query(query_embeddings=[vec], n_results=min(top_k, self.count()), where=where or None)
        out = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append(RetrievedChunk(chunk=_chunk(cid, doc, meta), score=round(1.0 - float(dist), 4)))
        return out

    def all_chunks(self, where: dict | None = None) -> list[Chunk]:
        res = self.col.get(where=where or None, include=["documents", "metadatas"])
        chunks = [_chunk(i, d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]
        return sorted(chunks, key=lambda c: (c.source_filename, c.chunk_index))

    def get(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        res = self.col.get(ids=chunk_ids, include=["documents", "metadatas"])
        return [_chunk(i, d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]


def _meta(c: Chunk) -> dict:
    m = {"document_id": c.document_id, "source_filename": c.source_filename, "chunk_index": c.chunk_index,
         "content_type": c.content_type, "content_hash": c.metadata.get("content_hash", ""),
         "file_type": c.metadata.get("file_type", ""), "extra": json.dumps(c.metadata)}
    for k in ("page", "row_start", "row_end", "section"):
        v = getattr(c, k)
        if v is not None:
            m[k] = v
    return m


def _chunk(cid: str, doc: str, m: dict) -> Chunk:
    return Chunk(chunk_id=cid, document_id=m.get("document_id", ""), source_filename=m.get("source_filename", ""),
                 text=doc, page=m.get("page"), row_start=m.get("row_start"), row_end=m.get("row_end"),
                 section=m.get("section"), chunk_index=int(m.get("chunk_index", 0)),
                 content_type=m.get("content_type", "prose"), metadata=json.loads(m.get("extra", "{}")))
