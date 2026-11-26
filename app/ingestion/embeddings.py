"""Sentence embeddings.

Primary backend: `sentence-transformers`.  On machines where PyTorch cannot be
loaded (for example Windows Smart App Control blocking torch DLLs) the same
sentence-transformers model is executed through ONNX Runtime using the ONNX
export published in the model repository (mean pooling + L2 normalisation,
identical to the model's sentence-transformers pooling config).
"""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from app.config import get_settings

log = logging.getLogger("forgeai.embeddings")


class Embedder:
    backend: str = ""
    model_name: str = ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(Embedder):
    backend = "sentence-transformers"

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # may raise OSError if torch is blocked
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()


class OnnxSentenceEmbedder(Embedder):
    backend = "onnxruntime"

    def __init__(self, model_name: str, max_len: int = 256):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.model_name = model_name
        onnx_path = hf_hub_download(model_name, "onnx/model.onnx")
        tok_path = hf_hub_download(model_name, "tokenizer.json")
        self.tokenizer = Tokenizer.from_file(tok_path)
        self.tokenizer.enable_truncation(max_length=max_len)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self.session.get_inputs()}

    def embed(self, texts):
        out: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            enc = self.tokenizer.encode_batch(batch)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feeds)[0]  # (b, seq, dim)
            m = mask[..., None].astype(np.float32)
            pooled = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            out.extend(pooled.tolist())
        return out


@lru_cache
def get_embedder() -> Embedder:
    name = get_settings().embedding_model
    try:
        e: Embedder = SentenceTransformerEmbedder(name)
    except Exception as err:  # noqa: BLE001  (OSError when torch DLLs are blocked, ImportError, ...)
        log.warning("sentence-transformers unavailable (%s); using ONNX Runtime for %s", str(err)[:120], name)
        e = OnnxSentenceEmbedder(name)
    log.info("embedding backend: %s (%s)", e.backend, name)
    return e
