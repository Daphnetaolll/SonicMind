from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SourceType = Literal["local", "site", "web"]
TrustLevel = Literal["high", "medium", "low"]
SufficiencyLabel = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]
CertaintyLabel = Literal["CONFIDENT", "PARTIAL", "UNCERTAIN"]


@dataclass
class EvidenceItem:
    rank: int
    source_type: SourceType
    source_name: str
    title: str
    snippet: str
    full_text: str
    retrieval_score: float
    trust_level: TrustLevel
    url: str | None = None
    chunk_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class EvidenceAssessment:
    label: SufficiencyLabel
    reasons: list[str]
    evidence_count: int
    top_score: float
    keyword_coverage: float


@dataclass
class Citation:
    number: int
    title: str
    source_type: SourceType
    source_name: str
    url: str | None


@dataclass
class AnswerSynthesis:
    answer: str
    certainty: CertaintyLabel
    uncertainty_note: str | None
    citations: list[Citation]

