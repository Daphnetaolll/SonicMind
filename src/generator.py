from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable
from urllib import error, request

from src.evidence import AnswerSynthesis, Citation, EvidenceAssessment, EvidenceItem
from src.memory import ChatTurn, format_chat_history
from src.music.schemas import MusicRoutingResult
from src.retriever import RetrievalResult


DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant that answers questions using the provided evidence. "
    "Prefer local knowledge-base evidence first, then trusted sites, then broader web evidence. "
    "Do not invent facts that are not supported by evidence. "
    "If the evidence is incomplete or conflicting, say so clearly. "
    "Keep answers concise, accurate, and grounded in the provided sources."
)


@dataclass
class LLMConfig:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 60
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "LLMConfig":
        # Centralize OpenAI-compatible settings so app code never handles raw API configuration.
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing LLM_API_KEY (or OPENAI_API_KEY).")

        model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or cls.base_url
        timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            temperature=temperature,
        )


def format_context(results: Iterable[RetrievalResult]) -> str:
    # Legacy document formatting is kept for CLI helpers that call generate_answer directly.
    sections: list[str] = []
    for item in results:
        source = item.title or item.path or item.chunk_id
        sections.append(
            f"[Document {item.rank}] source={source} score={item.score:.4f}\n{item.text.strip()}"
        )
    return "\n\n".join(sections)


def format_evidence_context(evidence: Iterable[EvidenceItem]) -> str:
    # Number evidence blocks so the model can return citation ids that map back to source cards.
    sections: list[str] = []
    for idx, item in enumerate(evidence, start=1):
        url = item.url or "n/a"
        sections.append(
            f"[Evidence {idx}] "
            f"type={item.source_type} trust={item.trust_level} score={item.retrieval_score:.4f} "
            f"title={item.title} source={item.source_name} url={url}\n"
            f"{item.full_text.strip()}"
        )
    return "\n\n".join(sections)


def build_user_prompt(
    query: str,
    context: str,
    chat_history: list[ChatTurn] | None = None,
) -> str:
    # Build the older document-only prompt used by CLI scripts and compatibility helpers.
    history_block = format_chat_history(chat_history or [])
    history_section = ""
    if history_block:
        history_section = f"Recent conversation:\n{history_block}\n\n"

    return (
        "Answer the user's question using only the evidence below.\n\n"
        "Requirements:\n"
        "1. Use only the provided evidence.\n"
        "2. Prefer local evidence over site evidence, and site evidence over web evidence.\n"
        "3. If the evidence is insufficient, say so directly and explain what is missing.\n"
        "4. Resolve pronouns using the recent conversation when possible.\n\n"
        f"{history_section}"
        f"User question: {query}\n\n"
        "Evidence:\n"
        f"{context}"
    )


def build_synthesis_prompt(
    query: str,
    context: str,
    assessment: EvidenceAssessment,
    chat_history: list[ChatTurn] | None = None,
    music_routing: MusicRoutingResult | None = None,
) -> str:
    # Build the main grounded-answer prompt with evidence assessment and optional music routing details.
    history_block = format_chat_history(chat_history or [])
    history_section = ""
    if history_block:
        history_section = f"Recent conversation:\n{history_block}\n\n"

    reasons = "\n".join(f"- {reason}" for reason in assessment.reasons)
    music_section = ""
    if music_routing:
        understanding = music_routing.query_understanding
        ranked_lines = []
        for idx, entity in enumerate(music_routing.ranked_entities[:8], start=1):
            genres = ", ".join(entity.genres[:3]) if entity.genres else "n/a"
            sources = ", ".join(entity.sources[:3]) if entity.sources else "evidence-derived"
            related = ", ".join(item.name for item in entity.related_entities[:4]) or "n/a"
            ranked_lines.append(
                f"{idx}. {entity.name} | type={entity.type} | score={entity.score:.2f} | "
                f"genres={genres} | related={related} | sources={sources}"
            )
        track_lines = []
        plan = music_routing.recommendation_plan
        for idx, track in enumerate(plan.candidate_tracks[:8], start=1):
            sources = ", ".join(track.source_names[:3]) or track.source_type
            track_lines.append(
                f"{idx}. {track.artist} - {track.title} | score={track.score:.2f} | "
                f"sources={sources} | reason={track.reason}"
            )
        music_section = (
            "Structured music findings extracted from trusted evidence and dynamic music-source discovery:\n"
            f"Intent: {understanding.intent}\n"
            f"Primary entity type: {understanding.primary_entity_type}\n"
            f"Genre hint: {understanding.genre_hint or 'n/a'}\n"
            f"Recommendation question type: {plan.question_type}\n"
            f"Recommendation confidence: {plan.confidence}\n"
            f"Recommendation uncertainty: {plan.uncertainty_note or 'n/a'}\n"
            "Ranked entities:\n"
            + ("\n".join(ranked_lines) if ranked_lines else "n/a")
            + "\nCandidate tracks used for Spotify display:\n"
            + ("\n".join(track_lines) if track_lines else "n/a")
            + "\n\n"
        )

    return (
        "Produce a grounded answer from the supplied evidence.\n\n"
        "Return only valid JSON with this schema:\n"
        '{"answer":"string","certainty":"CONFIDENT|PARTIAL|UNCERTAIN","uncertainty_note":"string","citations":[1,2]}\n\n'
        "Requirements:\n"
        "1. Use only supplied evidence.\n"
        "2. Prefer local evidence, then trusted site evidence, then broader web evidence.\n"
        "3. Use structured music findings when they are provided. If candidate tracks are listed, the written answer must refer to the same tracks that Spotify will display.\n"
        "4. If evidence conflicts or is incomplete, certainty must be PARTIAL or UNCERTAIN.\n"
        "5. Keep the answer concise and practical.\n"
        "6. citations must contain evidence numbers that support the answer.\n\n"
        f"Assessment label: {assessment.label}\n"
        f"Assessment reasons:\n{reasons}\n\n"
        f"{history_section}"
        f"{music_section}"
        f"User question: {query}\n\n"
        "Evidence:\n"
        f"{context}"
    )


def _extract_json_object(raw: str) -> dict | None:
    # Accept strict JSON first, then recover JSON objects wrapped in Markdown or extra model text.
    text = raw.strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _looks_like_unhelpful_answer(answer: str) -> bool:
    # Detect generic refusal text so structured music candidates can rescue otherwise weak answers.
    lowered = answer.lower()
    markers = (
        "does not specify",
        "does not provide",
        "cannot provide",
        "cannot determine",
        "not enough evidence",
        "insufficient evidence",
    )
    return any(marker in lowered for marker in markers)


def _structured_music_answer(query: str, music_routing: MusicRoutingResult) -> str:
    # Fallback answer keeps text output aligned with the same music candidates used for Spotify cards.
    understanding = music_routing.query_understanding
    track_candidates = music_routing.recommendation_plan.candidate_tracks[:6]
    if track_candidates:
        names = ", ".join(f"{track.artist} - {track.title}" for track in track_candidates)
        if music_routing.recommendation_plan.question_type == "trending_tracks":
            answer = f"For {understanding.genre_hint or 'this style'}, the strongest current track candidates I found are {names}."
        else:
            answer = f"For {understanding.genre_hint or 'this style'}, the strongest track candidates I found are {names}."

        details: list[str] = []
        for track in track_candidates[:4]:
            sources = ", ".join(track.source_names[:3]) or track.source_type
            details.append(f"{track.artist} - {track.title} is supported by {sources}.")
        return answer + " " + " ".join(details)

    entities = music_routing.ranked_entities[:6]
    if not entities:
        return ""

    names = ", ".join(entity.name for entity in entities)
    if understanding.intent == "label_recommendation":
        answer = f"For {understanding.genre_hint or 'this style'}, the strongest label candidates are {names}."
    elif understanding.intent == "artist_recommendation":
        answer = f"For {understanding.genre_hint or 'this style'}, the strongest artist candidates are {names}."
    elif understanding.intent == "track_recommendation":
        answer = f"For {understanding.genre_hint or 'this style'}, the strongest track candidates are {names}."
    else:
        answer = f"The most relevant music entities I found are {names}."

    details: list[str] = []
    for entity in entities[:4]:
        related = ", ".join(item.name for item in entity.related_entities[:4])
        sources = ", ".join(entity.sources[:3]) or "trusted evidence"
        detail = f"{entity.name} is supported by {sources}"
        if related:
            detail += f"; related artists/entities include {related}"
        details.append(detail + ".")

    return answer + " " + " ".join(details)


def call_chat_completion(
    *,
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, str] | None = None,
) -> str:
    # Use a raw OpenAI-compatible chat completion request to avoid adding a heavier SDK dependency.
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format:
        payload["response_format"] = response_format

    req = request.Request(
        url=f"{config.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=config.timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

    data = json.loads(raw)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {data}") from exc


def generate_answer(
    query: str,
    results: Iterable[RetrievalResult],
    *,
    chat_history: list[ChatTurn] | None = None,
    config: LLMConfig | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> str:
    docs = list(results)
    if not docs:
        return "Based on the current knowledge base, I cannot determine that."

    llm_config = config or LLMConfig.from_env()
    context = format_context(docs)
    user_prompt = build_user_prompt(query, context, chat_history=chat_history)
    return call_chat_completion(
        config=llm_config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def synthesize_answer(
    query: str,
    evidence: list[EvidenceItem],
    assessment: EvidenceAssessment,
    *,
    chat_history: list[ChatTurn] | None = None,
    config: LLMConfig | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    music_routing: MusicRoutingResult | None = None,
) -> AnswerSynthesis:
    if not evidence:
        return AnswerSynthesis(
            answer="I could not find enough reliable evidence to answer that confidently.",
            certainty="UNCERTAIN",
            uncertainty_note="No supporting evidence was available from the local knowledge base, trusted sites, or web search.",
            citations=[],
        )

    llm_config = config or LLMConfig.from_env()
    context = format_evidence_context(evidence)
    user_prompt = build_synthesis_prompt(
        query,
        context,
        assessment,
        chat_history=chat_history,
        music_routing=music_routing,
    )
    raw = call_chat_completion(
        config=llm_config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
    )

    parsed = _extract_json_object(raw)
    if parsed is None:
        parsed = {
            "answer": raw.strip(),
            "certainty": "PARTIAL" if assessment.label == "PARTIAL" else "UNCERTAIN",
            "uncertainty_note": "The answer could not be parsed as structured JSON, so citations could not be verified automatically.",
            "citations": [],
        }

    citation_ids = parsed.get("citations") or []
    citations: list[Citation] = []
    for ref in citation_ids:
        if isinstance(ref, int) and 1 <= ref <= len(evidence):
            item = evidence[ref - 1]
            citations.append(
                Citation(
                    number=ref,
                    title=item.title,
                    source_type=item.source_type,
                    source_name=item.source_name,
                    url=item.url,
                )
            )

    certainty = parsed.get("certainty", "UNCERTAIN")
    if certainty not in {"CONFIDENT", "PARTIAL", "UNCERTAIN"}:
        certainty = "UNCERTAIN"

    uncertainty_note = parsed.get("uncertainty_note") or None
    if assessment.label != "SUFFICIENT" and not uncertainty_note:
        uncertainty_note = "The available evidence does not fully cover the question."

    answer = str(parsed.get("answer", "")).strip()
    if music_routing and music_routing.ranked_entities and _looks_like_unhelpful_answer(answer):
        structured_answer = _structured_music_answer(query, music_routing)
        if structured_answer:
            answer = structured_answer
            certainty = "PARTIAL" if certainty == "UNCERTAIN" else certainty
            uncertainty_note = (
                "The answer uses the same structured music candidates that are passed to Spotify for display."
            )

    return AnswerSynthesis(
        answer=answer or "I could not synthesize a supported answer.",
        certainty=certainty,
        uncertainty_note=uncertainty_note,
        citations=citations,
    )
