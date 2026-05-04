from __future__ import annotations

import re
from collections import Counter

from src.evidence import EvidenceAssessment, EvidenceItem


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
    "how", "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to",
    "was", "what", "when", "where", "which", "who", "why", "with", "music",
}


def _keywords(text: str) -> list[str]:
    # Reduce questions to meaningful keywords for a lightweight evidence coverage check.
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower())
        if token not in STOPWORDS and len(token) > 2
    ]


def assess_evidence_sufficiency(query: str, evidence: list[EvidenceItem]) -> EvidenceAssessment:
    # Classify whether retrieved evidence is strong enough before escalating to broader sources.
    if not evidence:
        return EvidenceAssessment(
            label="INSUFFICIENT",
            reasons=["No evidence was retrieved."],
            evidence_count=0,
            top_score=0.0,
            keyword_coverage=0.0,
        )

    query_keywords = _keywords(query)
    evidence_text = " ".join(item.title + " " + item.full_text for item in evidence).lower()
    matched_keywords = [keyword for keyword in query_keywords if keyword in evidence_text]
    keyword_coverage = (len(set(matched_keywords)) / len(set(query_keywords))) if query_keywords else 1.0
    top_score = max(item.retrieval_score for item in evidence)
    type_counts = Counter(item.source_type for item in evidence)

    # Explain the label in user-visible diagnostics instead of returning only a score.
    reasons: list[str] = []
    if keyword_coverage >= 0.75:
        reasons.append("Most query keywords are covered by the retrieved evidence.")
    elif keyword_coverage >= 0.4:
        reasons.append("The retrieved evidence covers part of the query, but not all of it.")
    else:
        reasons.append("The retrieved evidence has weak keyword coverage for the query.")

    if type_counts.get("local"):
        reasons.append("Local knowledge base evidence was found.")

    if top_score >= 0.72 and keyword_coverage >= 0.6 and len(evidence) >= 2:
        return EvidenceAssessment(
            label="SUFFICIENT",
            reasons=reasons,
            evidence_count=len(evidence),
            top_score=top_score,
            keyword_coverage=keyword_coverage,
        )

    if top_score >= 0.5 and keyword_coverage >= 0.3:
        return EvidenceAssessment(
            label="PARTIAL",
            reasons=reasons,
            evidence_count=len(evidence),
            top_score=top_score,
            keyword_coverage=keyword_coverage,
        )

    return EvidenceAssessment(
        label="INSUFFICIENT",
        reasons=reasons,
        evidence_count=len(evidence),
        top_score=top_score,
        keyword_coverage=keyword_coverage,
    )
