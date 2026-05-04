from __future__ import annotations

from dataclasses import dataclass

from src.evidence import EvidenceAssessment, EvidenceItem
from src.retrievers import retrieve_local_evidence, retrieve_site_evidence, retrieve_web_evidence
from src.retriever import RetrievalResult
from src.services.evidence_service import assess_evidence_sufficiency


@dataclass
class RoutingResult:
    local_assessment: EvidenceAssessment
    final_assessment: EvidenceAssessment
    local_evidence: list[EvidenceItem]
    site_evidence: list[EvidenceItem]
    web_evidence: list[EvidenceItem]
    used_evidence: list[EvidenceItem]
    retrieved_documents: list[RetrievalResult]
    reranked_documents: list[RetrievalResult]
    route_steps: list[str]


def route_evidence(
    query: str,
    *,
    topk: int,
    candidate_k: int,
    model_name: str,
) -> RoutingResult:
    local_evidence, retrieved_documents, reranked_documents = retrieve_local_evidence(
        query,
        topk=topk,
        candidate_k=candidate_k,
        model_name=model_name,
    )
    local_assessment = assess_evidence_sufficiency(query, local_evidence)
    route_steps = [f"local:{local_assessment.label.lower()}"]

    if local_assessment.label == "SUFFICIENT":
        return RoutingResult(
            local_assessment=local_assessment,
            final_assessment=local_assessment,
            local_evidence=local_evidence,
            site_evidence=[],
            web_evidence=[],
            used_evidence=local_evidence,
            retrieved_documents=retrieved_documents,
            reranked_documents=reranked_documents,
            route_steps=route_steps,
        )

    try:
        site_evidence = retrieve_site_evidence(query)
    except (RuntimeError, ValueError):
        # External site search should degrade to local evidence instead of failing the whole answer.
        site_evidence = []
        route_steps.append("site:unavailable")
    combined_site = local_evidence + site_evidence
    site_assessment = assess_evidence_sufficiency(query, combined_site)
    if not route_steps[-1].startswith("site:"):
        route_steps.append(f"site:{site_assessment.label.lower()}")
    if site_assessment.label == "SUFFICIENT":
        return RoutingResult(
            local_assessment=local_assessment,
            final_assessment=site_assessment,
            local_evidence=local_evidence,
            site_evidence=site_evidence,
            web_evidence=[],
            used_evidence=combined_site,
            retrieved_documents=retrieved_documents,
            reranked_documents=reranked_documents,
            route_steps=route_steps,
        )

    try:
        web_evidence = retrieve_web_evidence(query)
    except (RuntimeError, ValueError):
        # General web search is best-effort; preserve partial local/site answers on provider failures.
        web_evidence = []
        route_steps.append("web:unavailable")
    combined_web = combined_site + web_evidence
    final_assessment = assess_evidence_sufficiency(query, combined_web)
    if not route_steps[-1].startswith("web:"):
        route_steps.append(f"web:{final_assessment.label.lower()}")
    return RoutingResult(
        local_assessment=local_assessment,
        final_assessment=final_assessment,
        local_evidence=local_evidence,
        site_evidence=site_evidence,
        web_evidence=web_evidence,
        used_evidence=combined_web,
        retrieved_documents=retrieved_documents,
        reranked_documents=reranked_documents,
        route_steps=route_steps,
    )
