"""Rule-runner for scoped syntax/semantic lint checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .ast_parser import ResumeAst

RuleFn = Callable[[ResumeAst, "RuleContext", Dict[str, Any]], List["RuleFinding"]]

ACTION_VERB_HINTS = {
    "achieved",
    "administered",
    "analyzed",
    "built",
    "collaborated",
    "created",
    "delivered",
    "designed",
    "developed",
    "directed",
    "established",
    "executed",
    "generated",
    "implemented",
    "improved",
    "increased",
    "launched",
    "led",
    "managed",
    "optimized",
    "organized",
    "produced",
    "reduced",
    "resolved",
    "streamlined",
}


@dataclass
class RuleContext:
    """Execution context for lint rules."""

    lang: str
    nlp: Any | None
    nlp_backend: str
    strict_scope: bool = True


@dataclass
class RuleFinding:
    """Rule finding with category and score impact."""

    rule_id: str
    category: str
    message: str
    evidence: str
    penalty: int


class RuleRunner:
    """Config-driven registry runner."""

    def __init__(self, rules: List[Dict[str, Any]], registry: Dict[str, RuleFn]):
        self.rules = rules
        self.registry = registry

    def run(self, ast: ResumeAst, context: RuleContext) -> List[RuleFinding]:
        findings: List[RuleFinding] = []
        for cfg in self.rules:
            if not bool(cfg.get("enabled", True)):
                continue

            rule_id = str(cfg.get("id", "")).strip()
            if not rule_id:
                continue
            rule_fn = self.registry.get(rule_id)
            if rule_fn is None:
                continue

            params = cfg.get("params", {}) or {}
            findings.extend(rule_fn(ast, context, params))
        return findings


def build_default_runner() -> RuleRunner:
    """Return runner with default production rules."""
    return RuleRunner(
        rules=[
            {
                "id": "bullet_starts_with_verb",
                "enabled": True,
                "params": {"penalty": 12, "max_nonverb_ratio": 0.35},
            },
            {
                "id": "low_metrics_density",
                "enabled": True,
                "params": {"penalty": 8, "min_ratio": 0.20},
            },
            {
                "id": "long_sentence_missing_punctuation",
                "enabled": True,
                "params": {"penalty": 4, "max_tokens": 28, "max_findings": 3},
            },
        ],
        registry={
            "bullet_starts_with_verb": _rule_bullet_starts_with_verb,
            "low_metrics_density": _rule_low_metrics_density,
            "long_sentence_missing_punctuation": _rule_long_sentence_missing_punctuation,
        },
    )


def _target_bullets(ast: ResumeAst, context: RuleContext) -> List[str]:
    if not context.strict_scope:
        return ast.bullets
    if not ast.has_experience_section:
        return []
    return ast.get_experience_bullets()


def _rule_low_metrics_density(ast: ResumeAst, context: RuleContext, params: Dict[str, Any]) -> List[RuleFinding]:
    bullets = [b for b in _target_bullets(ast, context) if b.strip()]
    if not bullets:
        return []

    penalty = int(params.get("penalty", 8))
    min_ratio = float(params.get("min_ratio", 0.2))
    metric_re = re.compile(r"\b\d+(?:\.\d+)?%?\b|\$\d+[\d,]*\b|\b\d+\+")

    hits = sum(1 for b in bullets if metric_re.search(b))
    ratio = hits / len(bullets)
    if ratio >= min_ratio:
        return []

    return [
        RuleFinding(
            rule_id="low_metrics_density",
            category="keywords",
            message=f"Only {hits}/{len(bullets)} experience bullets include numeric evidence.",
            evidence="Add measurable impact where possible (%, $, counts, time).",
            penalty=penalty,
        )
    ]


def _rule_bullet_starts_with_verb(ast: ResumeAst, context: RuleContext, params: Dict[str, Any]) -> List[RuleFinding]:
    if context.lang != "en":
        return []
    if context.nlp is None:
        return []
    if "tagger" not in getattr(context.nlp, "pipe_names", []):
        return []

    bullets = [b for b in _target_bullets(ast, context) if b.strip()]
    if not bullets:
        return []

    penalty = int(params.get("penalty", 12))
    max_nonverb_ratio = float(params.get("max_nonverb_ratio", 0.35))

    checked = 0
    bad: List[str] = []
    for bullet in bullets:
        doc = context.nlp(bullet)
        first = None
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            if token.like_num:
                first = None
                break
            first = token
            break
        if first is None:
            continue

        checked += 1
        first_text = first.text.lower()
        first_lemma = first.lemma_.lower() if first.lemma_ else first_text
        looks_like_action_verb = (
            first.pos_ == "VERB" or first_text in ACTION_VERB_HINTS or first_lemma in ACTION_VERB_HINTS
        )
        if not looks_like_action_verb:
            bad.append(bullet)

    if checked == 0:
        return []
    if (len(bad) / checked) <= max_nonverb_ratio:
        return []

    return [
        RuleFinding(
            rule_id="bullet_starts_with_verb",
            category="keywords",
            message=f"{len(bad)}/{checked} experience bullets do not start with an action verb.",
            evidence=bad[0][:140],
            penalty=penalty,
        )
    ]


def _rule_long_sentence_missing_punctuation(
    ast: ResumeAst,
    context: RuleContext,
    params: Dict[str, Any],
) -> List[RuleFinding]:
    bullets = [b for b in _target_bullets(ast, context) if b.strip()]
    if not bullets:
        return []

    penalty = int(params.get("penalty", 4))
    max_tokens = int(params.get("max_tokens", 28))
    max_findings = int(params.get("max_findings", 3))
    punct = str(params.get("punctuation", ".,!?;:。！？；："))

    findings: List[RuleFinding] = []
    for bullet in bullets:
        tokens = re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", bullet)
        if len(tokens) <= max_tokens:
            continue
        if any(ch in bullet for ch in punct):
            continue
        findings.append(
            RuleFinding(
                rule_id="long_sentence_missing_punctuation",
                category="structure",
                message=f"Long experience bullet ({len(tokens)} tokens/chars) without punctuation.",
                evidence=bullet[:140],
                penalty=penalty,
            )
        )
        if len(findings) >= max_findings:
            break

    return findings
