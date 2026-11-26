"""Retrieval according to an agent's retrieval_config."""
from __future__ import annotations

from app.core.schemas import AgentDefinition, RetrievedChunk
from app.ingestion.pipeline import KnowledgeBase
from app.ingestion.vector_store import VectorStore


class Retriever:
    def __init__(self, agent: AgentDefinition):
        self.agent = agent
        cfg = agent.retrieval_config
        col = cfg.collection_name or KnowledgeBase(agent.project_id).ensure_index(cfg)
        # if the configured collection does not exist yet (e.g. optimizer changed chunking), build it
        if cfg.collection_name and VectorStore(col).count() == 0:
            col = KnowledgeBase(agent.project_id).ensure_index(cfg)
        self.store = VectorStore(col)
        self.collection = col

    def retrieve(self, query: str) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
        """Returns (accepted hits above threshold, all hits) restricted to approved sources."""
        cfg = self.agent.retrieval_config
        where = dict(cfg.metadata_filters) if cfg.metadata_filters else None
        hits = self.store.query(query, cfg.top_k, where=where)
        allowed = set(self.agent.knowledge_sources)
        hits = [h for h in hits if not allowed or h.chunk.source_filename in allowed]
        accepted = [h for h in hits if h.score >= cfg.similarity_threshold]
        return accepted, hits
