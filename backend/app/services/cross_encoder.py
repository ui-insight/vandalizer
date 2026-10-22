"""A local cross-encoder that scores how well a passage answers a query.

Knowledge-base retrieval ranks candidates with a bi-encoder, which embeds the
query and every passage separately and so cannot tell "the de minimis rate"
from "one-time extension of indirect rates" when both are about rates. A
cross-encoder reads the query and the passage together and scores the pair;
on the retrieval gold set it is what made a relevance cut possible at all
(a cosine floor that silenced unanswerable queries also dropped the right
section for one answerable query in five).

The model is ms-marco-MiniLM-L-6-v2 as an ONNX export, run with onnxruntime
and tokenizers, which the image already carries for Chroma's embedder: no
torch, about 90 MB. Its files are pinned to a revision and verified by
sha256 before use; a file that does not match is refused, not loaded. The
image bakes them in (``python -m app.services.cross_encoder``); without that
the first scoring call downloads them, like Chroma's own model.

Scores are raw logits: higher is more relevant, about -11 for an unrelated
passage and +9 for a direct answer. Callers compare them with fixed cuts, so
the model, its revision and the input format are part of the contract.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_REPO = "Xenova/ms-marco-MiniLM-L-6-v2"
MODEL_REVISION = "a09144355adeed5f58c8ed011d209bf8ee5a1fec"
# The files the scorer reads, with their sha256 at MODEL_REVISION.
MODEL_FILES = {
    "onnx/model.onnx": "c623d0bcb99f4622beb413eaef00cfbe5db20df9f1dd982da4b4f26022881870",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "config.json": "d827779a72d27ae68cf878a6fc2e954542663fe21ca515d9f4783fc96be2d37e",
    "tokenizer_config.json": "0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53",
}
# Model input limit; a pair longer than this is truncated longest-first.
MAX_TOKENS = 512
# Passages are cut to this many characters before tokenizing, so a long one
# keeps its opening rather than being trimmed by the tokenizer alone.
MAX_PASSAGE_CHARS = 1500
BATCH_SIZE = 16
DOWNLOAD_TIMEOUT_S = 60

_LOCK = threading.Lock()
_SCORER: "CrossEncoder | None" = None
_FAILED = False


class ModelUnavailable(RuntimeError):
    """The model files are missing, failed verification, or would not load."""


def model_dir() -> Path:
    from app.config import Settings

    configured = (Settings().kb_reranker_dir or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent.parent / "models" / "ms-marco-MiniLM-L-6-v2"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _verified(path: Path, digest: str) -> bool:
    return path.is_file() and _sha256(path) == digest


def ensure_model(directory: Optional[Path] = None, *, download: bool = True) -> Path:
    import httpx

    """The verified model directory, downloading what is missing.

    Every file is checked against its pinned sha256; a mismatching download
    is deleted and refused. Raises :class:`ModelUnavailable`.
    """
    directory = directory or model_dir()
    for name, digest in MODEL_FILES.items():
        path = directory / name
        if _verified(path, digest):
            continue
        if not download:
            raise ModelUnavailable(f"reranker file {name} is missing or does not match its pinned hash")
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        try:
            # The Hub answers a pinned file with a redirect to its CDN.
            with (
                httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as resp,
                open(partial, "wb") as out,
            ):
                resp.raise_for_status()
                for block in resp.iter_bytes(1 << 20):
                    out.write(block)
        except Exception as e:  # noqa: BLE001
            partial.unlink(missing_ok=True)
            raise ModelUnavailable(f"could not download reranker file {name}: {e}") from e
        if _sha256(partial) != digest:
            partial.unlink(missing_ok=True)
            raise ModelUnavailable(f"reranker file {name} failed verification (sha256 mismatch)")
        os.replace(partial, path)
    return directory


class CrossEncoder:
    """Scores (query, passage) pairs with the ONNX model in ``directory``."""

    def __init__(self, directory: Path, *, threads: int = 4):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        tok_config = json.loads((directory / "tokenizer_config.json").read_text(encoding="utf-8"))
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=min(MAX_TOKENS, int(tok_config.get("model_max_length") or MAX_TOKENS)))
        self.tokenizer.enable_padding(pad_id=int(config.get("pad_token_id", 0)), pad_token=tok_config.get("pad_token", "[PAD]"))
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, threads)
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(directory / "onnx" / "model.onnx"), sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_names = {i.name for i in self.session.get_inputs()}

    def scores(self, query: str, passages: list[str]) -> list[float]:
        import numpy as np

        out: list[float] = []
        for start in range(0, len(passages), BATCH_SIZE):
            batch = passages[start:start + BATCH_SIZE]
            enc = self.tokenizer.encode_batch([(query, p[:MAX_PASSAGE_CHARS]) for p in batch])
            feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64)}
            if "attention_mask" in self.input_names:
                feed["attention_mask"] = np.array([e.attention_mask for e in enc], dtype=np.int64)
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
            logits = self.session.run(None, feed)[0]
            out.extend(float(v) for v in logits[:, 0])
        return out


def get_cross_encoder() -> Optional[CrossEncoder]:
    """The process-wide scorer, or None when it cannot be had.

    A failure to fetch or load is logged once and remembered for the life of
    the process, so retrieval falls back to its vector ranking instead of
    retrying a download on every query.
    """
    global _SCORER, _FAILED
    if _SCORER is not None or _FAILED:
        return _SCORER
    with _LOCK:
        if _SCORER is not None or _FAILED:
            return _SCORER
        try:
            from app.config import Settings

            settings = Settings()
            directory = ensure_model(download=True)
            _SCORER = CrossEncoder(directory, threads=settings.kb_reranker_threads)
        except Exception as e:  # noqa: BLE001 — retrieval degrades, never fails
            _FAILED = True
            logger.warning("Knowledge-base reranker unavailable; using vector ranking: %s", e)
        return _SCORER


if __name__ == "__main__":  # Baked into the image: python -m app.services.cross_encoder
    print(ensure_model())
