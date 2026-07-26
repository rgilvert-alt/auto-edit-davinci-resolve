"""ONNX CLIP semantic tagging (no PyTorch — macOS x86_64 / Python 3.13).

Downloads Xenova/clip-vit-base-patch32 ONNX weights into ``~/.autoedit/models/``
on first use. Soft-fails with a clear warning when onnxruntime/tokenizers are
missing or the model cannot be fetched.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .frames import FRAME_SIZE

HF_BASE = (
    "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main"
)
MODEL_FILES = {
    "vision_model.onnx": f"{HF_BASE}/onnx/vision_model.onnx",
    "text_model.onnx": f"{HF_BASE}/onnx/text_model.onnx",
    "tokenizer.json": f"{HF_BASE}/tokenizer.json",
    "config.json": f"{HF_BASE}/config.json",
}

# Curated adventure / action vocabulary for zero-shot tagging.
ADVENTURE_VOCAB = [
    # subjects
    "motorcycle",
    "dirt bike",
    "ATV",
    "rider",
    "person",
    "group of people",
    "helmet",
    # environments
    "forest trail",
    "gravel road",
    "mountain pass",
    "open landscape",
    "muddy track",
    "rocky terrain",
    "river crossing",
    "campsite",
    "village",
    "skyline",
    # shot types
    "POV riding shot",
    "wide establishing shot",
    "close-up detail",
    "tracking shot",
    "aerial view",
    # conditions / energy
    "sunset light",
    "overcast weather",
    "rain",
    "dust",
    "bright daylight",
    "golden hour",
    # actions
    "riding fast",
    "climbing uphill",
    "descending",
    "resting",
    "talking",
]


@dataclass
class SemanticResult:
    embedding: np.ndarray | None  # (512,) or (768,) float32 L2-normalized
    tags: list[tuple[str, float]]  # (label, score) descending
    warning: str | None = None


def models_dir() -> Path:
    root = Path.home() / ".autoedit" / "models" / "clip-vit-base-patch32"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_models() -> Path:
    """Download missing ONNX + tokenizer files. Raises on hard failure."""
    root = models_dir()
    for name, url in MODEL_FILES.items():
        dest = root / name
        if dest.is_file() and dest.stat().st_size > 1000:
            continue
        _download(url, dest)
    return root


def available() -> tuple[bool, str | None]:
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError as exc:
        return False, (
            "Semantic tagging unavailable: install onnxruntime and tokenizers "
            f"({exc})"
        )
    try:
        ensure_models()
    except Exception as exc:  # pragma: no cover - network
        return False, f"Semantic tagging unavailable: {exc}"
    return True, None


def embed_frames(frames: np.ndarray) -> np.ndarray:
    """Return L2-normalized image embeddings, shape (n, dim)."""
    session = _vision_session()
    pixels = _preprocess_images(frames)
    out = session.run(None, {_vision_input_name(session): pixels})
    feats = _pick_embedding(out)
    return _l2_normalize(feats)


def embed_text(texts: list[str]) -> np.ndarray:
    """Return L2-normalized text embeddings, shape (n, dim)."""
    session = _text_session()
    tokenizer = _tokenizer()
    ids, mask = _tokenize(tokenizer, texts)
    feeds = {}
    for inp in session.get_inputs():
        name = inp.name.lower()
        if "mask" in name:
            feeds[inp.name] = mask
        else:
            feeds[inp.name] = ids
    out = session.run(None, feeds)
    feats = _pick_embedding(out)
    return _l2_normalize(feats)


def zero_shot_tags(
    frames: np.ndarray,
    vocabulary: list[str] | None = None,
    *,
    top_k: int = 5,
) -> SemanticResult:
    """Tag a set of frames by mean-pooling their CLIP embeddings."""
    ok, warning = available()
    if not ok:
        return SemanticResult(embedding=None, tags=[], warning=warning)

    vocab = vocabulary or ADVENTURE_VOCAB
    try:
        img = embed_frames(frames)
        if len(img) == 0:
            return SemanticResult(None, [], "No frames to embed")
        image_vec = _l2_normalize(img.mean(axis=0, keepdims=True))[0]
        text_vecs = _vocab_embeddings(tuple(vocab))
        scores = text_vecs @ image_vec
        order = np.argsort(-scores)
        tags = [(vocab[i], float(scores[i])) for i in order[:top_k]]
        return SemanticResult(embedding=image_vec.astype(np.float32), tags=tags)
    except Exception as exc:  # pragma: no cover - model quirks
        return SemanticResult(
            embedding=None, tags=[], warning=f"CLIP inference failed: {exc}"
        )


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    return float(np.dot(a, b))


# --- internals -------------------------------------------------------------


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    req = urllib.request.Request(url, headers={"User-Agent": "autoedit/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)


@lru_cache(maxsize=1)
def _vision_session():
    import onnxruntime as ort

    root = ensure_models()
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = 2
    return ort.InferenceSession(
        str(root / "vision_model.onnx"),
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )


@lru_cache(maxsize=1)
def _text_session():
    import onnxruntime as ort

    root = ensure_models()
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = 2
    return ort.InferenceSession(
        str(root / "text_model.onnx"),
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )


@lru_cache(maxsize=1)
def _tokenizer():
    from tokenizers import Tokenizer

    root = ensure_models()
    return Tokenizer.from_file(str(root / "tokenizer.json"))


@lru_cache(maxsize=1)
def _vocab_embeddings(vocab: tuple[str, ...]) -> np.ndarray:
    prompts = [f"a photo of {label}" for label in vocab]
    return embed_text(prompts)


def _vision_input_name(session) -> str:
    return session.get_inputs()[0].name


def _preprocess_images(frames: np.ndarray) -> np.ndarray:
    """CLIP image preprocess: RGB uint8 HxWx3 -> float32 NCHW normalized."""
    if frames.ndim == 3:
        frames = frames[None, ...]
    x = frames.astype(np.float32) / 255.0
    # Resize already 224; center crop done at sample time.
    mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
    std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
    x = (x - mean) / std
    # NHWC -> NCHW
    return np.transpose(x, (0, 3, 1, 2)).astype(np.float32)


def _tokenize(tokenizer, texts: list[str], max_length: int = 77):
    ids_list = []
    mask_list = []
    for text in texts:
        encoded = tokenizer.encode(text)
        ids = list(encoded.ids)[:max_length]
        # CLIP BOS/EOS usually already in tokenizer; pad to max_length
        attn = [1] * len(ids)
        while len(ids) < max_length:
            ids.append(0)
            attn.append(0)
        ids_list.append(ids)
        mask_list.append(attn)
    return (
        np.asarray(ids_list, dtype=np.int64),
        np.asarray(mask_list, dtype=np.int64),
    )


def _pick_embedding(outputs: list) -> np.ndarray:
    """Prefer pooler / embeds output; fall back to mean of last_hidden_state."""
    # Try 2-d outputs first (batch, dim)
    candidates = []
    for out in outputs:
        arr = np.asarray(out)
        if arr.ndim == 2:
            candidates.append(arr)
        elif arr.ndim == 3:
            # (batch, seq, dim) -> mean pool over seq
            candidates.append(arr.mean(axis=1))
    if not candidates:
        raise RuntimeError("CLIP model returned no usable embedding tensors")
    # Prefer smaller projection-sized vectors when multiple exist
    candidates.sort(key=lambda a: a.shape[-1])
    return candidates[0].astype(np.float32)


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        n = float(np.linalg.norm(x)) or 1.0
        return x / n
    norms = np.linalg.norm(x, axis=-1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    return x / norms


def encode_embedding_b64(vec: np.ndarray | None) -> str | None:
    if vec is None:
        return None
    import base64

    raw = np.asarray(vec, dtype=np.float16).tobytes()
    return base64.b64encode(raw).decode("ascii")


def decode_embedding_b64(data: str | None) -> np.ndarray | None:
    if not data:
        return None
    import base64

    raw = base64.b64decode(data.encode("ascii"))
    return np.frombuffer(raw, dtype=np.float16).astype(np.float32)
