"""Language routing and optional NLP backend loading."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

SUPPORTED_LANGS = {"en", "zh"}


@dataclass
class LangDecision:
    """Language routing outcome."""

    lang: str
    detector: str
    nlp: Optional[Any]
    nlp_backend: str


def decide_language(content: str, requested_lang: str = "auto", enable_nlp: bool = True) -> LangDecision:
    """Resolve lint language and optional NLP backend."""
    lang, detector = detect_language(content, requested_lang=requested_lang)
    nlp, backend = load_optional_nlp(lang, enabled=enable_nlp)
    return LangDecision(lang=lang, detector=detector, nlp=nlp, nlp_backend=backend)


def detect_language(content: str, requested_lang: str = "auto") -> tuple[str, str]:
    requested = (requested_lang or "auto").strip().lower()
    if requested in SUPPORTED_LANGS:
        return requested, "manual"
    if requested not in {"auto", ""}:
        return "en", "fallback:unsupported-manual"

    text = content.strip()
    if not text:
        return "en", "fallback:empty"

    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        detected = detect(text).lower()
        if detected.startswith("zh"):
            return "zh", "langdetect"
        if detected.startswith("en"):
            return "en", "langdetect"
    except Exception:
        pass

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if cjk_count > latin_count:
        return "zh", "heuristic"
    return "en", "heuristic"


def load_optional_nlp(lang: str, enabled: bool = True) -> tuple[Optional[Any], str]:
    if not enabled:
        return None, "disabled"
    if lang != "en":
        return None, "none"

    try:
        import spacy
    except Exception:
        return None, "none"

    try:
        nlp = spacy.load("en_core_web_sm")
        return nlp, "spacy:en_core_web_sm"
    except Exception:
        pass

    try:
        nlp = spacy.blank("en")
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        return nlp, "spacy:blank_en"
    except Exception:
        return None, "none"
