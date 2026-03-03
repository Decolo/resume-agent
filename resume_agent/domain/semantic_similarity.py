"""Local semantic similarity helpers for resume/JD matching.

This module keeps runtime dependencies minimal and deterministic by using
token-level + n-gram sparse vectors with cosine similarity.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

_TOKEN_SEPARATORS = " \t\r\n,;:!?()[]{}<>/\\|\"'`~@#$%^&*=+"

_CANONICAL_TERMS: Dict[str, str] = {
    "develop": "build",
    "developed": "build",
    "developing": "build",
    "built": "build",
    "building": "build",
    "create": "build",
    "created": "build",
    "implement": "build",
    "implemented": "build",
    "led": "lead",
    "leading": "lead",
    "managed": "lead",
    "management": "lead",
    "optimize": "improve",
    "optimized": "improve",
    "improved": "improve",
    "apis": "api",
    "restful": "api",
    "micro-services": "microservices",
    "microservice": "microservices",
    "k8s": "kubernetes",
    "ci/cd": "cicd",
    "pipeline": "cicd",
    "pipelines": "cicd",
    "deployed": "deployment",
    "deployments": "deployment",
    "services": "service",
    "systems": "system",
    "orchestration": "kubernetes",
    "http": "api",
    "interfaces": "api",
    "interface": "api",
    "server": "backend",
    "consumer": "client",
    "consumers": "client",
    "architecture": "system",
    "architectures": "system",
}


@dataclass
class SemanticBackendInfo:
    backend: str
    status: str
    reason: str = ""


def similarity_matrix(left_texts: List[str], right_texts: List[str]) -> tuple[List[List[float]], SemanticBackendInfo]:
    """Return pairwise similarity matrix in [0.0, 1.0]."""
    if not left_texts or not right_texts:
        return [], SemanticBackendInfo(backend="local-ngram", status="unavailable", reason="empty input")

    left_vectors = [_vectorize_text(text) for text in left_texts]
    right_vectors = [_vectorize_text(text) for text in right_texts]

    matrix: List[List[float]] = []
    for left in left_vectors:
        row = []
        for right in right_vectors:
            row.append(_cosine_sparse(left, right))
        matrix.append(row)

    return matrix, SemanticBackendInfo(backend="local-ngram", status="ok")


def _vectorize_text(text: str) -> Dict[str, float]:
    tokens = [_normalize_token(raw) for raw in _simple_tokenize(text)]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        return {}

    features: Counter[str] = Counter()
    for tok in tokens:
        features[f"tok:{tok}"] += 1.0
        if len(tok) >= 5:
            for i in range(len(tok) - 2):
                features[f"cg:{tok[i:i+3]}"] += 0.35

    for i in range(len(tokens) - 1):
        features[f"bg:{tokens[i]}_{tokens[i+1]}"] += 0.75

    return dict(features)


def _normalize_token(token: str) -> str:
    token = token.strip(".-_")
    if not token:
        return ""

    token = _CANONICAL_TERMS.get(token, token)
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 4 and token.endswith("es"):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s"):
        token = token[:-1]

    return _CANONICAL_TERMS.get(token, token)


def _simple_tokenize(text: str) -> List[str]:
    raw = []
    buffer: List[str] = []
    for ch in (text or "").lower():
        if ch in _TOKEN_SEPARATORS:
            if buffer:
                raw.append("".join(buffer))
                buffer = []
            continue
        buffer.append(ch)
    if buffer:
        raw.append("".join(buffer))
    return [piece for piece in raw if piece]


def _cosine_sparse(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    shared_keys = set(left.keys()) & set(right.keys())
    dot = sum(left[key] * right[key] for key in shared_keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return max(0.0, min(1.0, dot / (left_norm * right_norm)))
