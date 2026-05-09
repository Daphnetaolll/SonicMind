from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable
from urllib import error, request

from backend.services.memory_logging import log_memory
from src.evidence import AnswerSynthesis, Citation, EvidenceAssessment, EvidenceItem
from src.memory import ChatTurn, format_chat_history
from src.music.schemas import MusicRoutingResult
from src.retriever import RetrievalResult
from src.settings import resolve_runtime_settings


DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant that answers questions using the provided evidence. "
    "Prefer local knowledge-base evidence first, then trusted sites, then broader web evidence. "
    "Do not invent facts that are not supported by evidence. "
    "Answer in the same language as the user's question; for mixed-language questions, respond naturally in the dominant language. "
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
    remaining_chars = max(1200, resolve_runtime_settings().max_context_chars)
    for idx, item in enumerate(evidence, start=1):
        if remaining_chars <= 0:
            break

        url = item.url or "n/a"
        header = (
            f"[Evidence {idx}] "
            f"type={item.source_type} trust={item.trust_level} score={item.retrieval_score:.4f} "
            f"title={item.title} source={item.source_name} url={url}\n"
        )
        text_budget = max(0, remaining_chars - len(header))
        full_text = item.full_text.strip()
        if len(full_text) > text_budget:
            full_text = full_text[:text_budget].rstrip() + "..."
        block = f"{header}{full_text}"
        sections.append(block)
        remaining_chars -= len(block)
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
    if re.search(r"[\u4e00-\u9fff]", query):
        language_instruction = "The user used Chinese characters; answer in Chinese unless the question is clearly mixed-language."
    else:
        language_instruction = "Answer in the same language as the user's question."

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
        card_lines = []
        for idx, card in enumerate(music_routing.spotify_cards[:8], start=1):
            card_lines.append(
                f"{idx}. {card.card_type}: {card.title} | subtitle={card.subtitle} | "
                f"source_entity={card.source_entity or 'n/a'}"
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
            + "\nSpotify display cards:\n"
            + ("\n".join(card_lines) if card_lines else "n/a")
            + "\n\n"
        )
        if plan.question_type == "playlist_discovery":
            music_section += (
                "Playlist-style instruction: present the answer as an ordered listening path or DJ-set arc, "
                "starting softer when appropriate and ending with higher-energy picks when the user asks for progression.\n\n"
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
        "6. citations must contain evidence numbers that support the answer.\n"
        f"7. {language_instruction}\n\n"
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
        "couldn't find",
        "could not find",
        "couldn't find specific",
        "could not find specific",
        "does not specify",
        "does not provide",
        "cannot provide",
        "cannot determine",
        "not enough evidence",
        "insufficient evidence",
        "checking current charts",
        "music streaming platforms",
    )
    return any(marker in lowered for marker in markers)


def _answer_omits_recommendation_candidates(answer: str, music_routing: MusicRoutingResult) -> bool:
    # Recommendation answers must name the same track candidates used for Spotify cards.
    plan = music_routing.recommendation_plan
    if plan.question_type not in {"trending_tracks", "track_recommendation", "playlist_discovery"}:
        return False
    if not plan.candidate_tracks:
        return False

    lowered = answer.lower()
    for track in plan.candidate_tracks[:4]:
        if track.title.lower() in lowered or track.artist.lower() in lowered:
            return False
    return True


def _has_album_cards(music_routing: MusicRoutingResult) -> bool:
    # Album questions can be rescued from generic "not found" text using validated Spotify album cards.
    return any(card.card_type == "album" for card in music_routing.spotify_cards)


def _answer_omits_artist_track_cards(answer: str, music_routing: MusicRoutingResult) -> bool:
    # Artist top-track questions should name the same Spotify tracks shown in the UI.
    understanding = music_routing.query_understanding
    if understanding.intent != "artist_recommendation" or understanding.spotify_display_target != "artist_top_tracks":
        return False
    track_cards = [card for card in music_routing.spotify_cards if card.card_type == "track"]
    if not track_cards:
        return False

    lowered = answer.lower()
    for card in track_cards[:4]:
        if card.title.lower() in lowered:
            return False
    return True


def _uses_representative_fallback(music_routing: MusicRoutingResult) -> bool:
    # Curated/generated fallback tracks are useful examples, but they are not live chart verification.
    plan = music_routing.recommendation_plan
    if plan.question_type != "trending_tracks":
        return False
    if plan.uncertainty_note and "rather than verified current chart hits" in plan.uncertainty_note:
        return True
    return any("representative fallback" in track.reason.lower() for track in plan.candidate_tracks)


def _structured_music_answer(query: str, music_routing: MusicRoutingResult) -> str:
    # Fallback answer keeps text output aligned with the same music candidates used for Spotify cards.
    use_chinese = bool(re.search(r"[\u4e00-\u9fff]", query))
    understanding = music_routing.query_understanding
    album_cards = [card for card in music_routing.spotify_cards if card.card_type == "album"]
    if album_cards and understanding.spotify_display_target == "albums":
        names = ", ".join(f"{card.title} ({card.subtitle})" for card in album_cards[:4])
        artist = album_cards[0].source_entity
        if not artist and understanding.entities:
            artist = understanding.entities[0].name
        artist = artist or "that artist"
        if use_chinese:
            return f"我找到的 {artist} 相关热门专辑/作品候选是：{names}。这些卡片来自 Spotify 艺人目录和热门曲目的专辑信号。"
        return (
            f"For {artist}, the strongest Spotify album candidates I found are {names}. "
            "These cards come from Spotify artist-album data and top-track album signals."
        )

    artist_track_cards = [
        card
        for card in music_routing.spotify_cards
        if card.card_type == "track" and understanding.spotify_display_target == "artist_top_tracks"
    ]
    if artist_track_cards and understanding.intent == "artist_recommendation":
        names = ", ".join(f"{card.title} ({card.subtitle})" for card in artist_track_cards[:5])
        artist = artist_track_cards[0].source_entity
        if not artist and understanding.entities:
            artist = understanding.entities[0].name
        artist = artist or "that artist"
        if use_chinese:
            return f"我找到的 {artist} 热门歌曲候选是：{names}。这些卡片来自 Spotify 艺人热门曲目数据。"
        return f"For {artist}, the strongest Spotify popular-track candidates I found are {names}."

    track_candidates = music_routing.recommendation_plan.candidate_tracks[:6]
    representative_fallback = _uses_representative_fallback(music_routing)
    if track_candidates:
        names = ", ".join(f"{track.artist} - {track.title}" for track in track_candidates)
        if use_chinese:
            if representative_fallback:
                answer = (
                    f"我还没能验证 {understanding.genre_hint or '这种风格'} 的实时热门榜单曲目，"
                    f"但可以先给你这些有来源支撑的代表性选择：{names}。"
                )
            else:
                answer = f"针对 {understanding.genre_hint or '这种风格'}，我找到的最强曲目候选是 {names}。"
            details = []
            for track in track_candidates[:4]:
                sources = ", ".join(track.source_names[:3]) or track.source_type
                details.append(f"{track.artist} - {track.title} 由 {sources} 支持。")
            return answer + " " + " ".join(details)
        if representative_fallback:
            answer = (
                f"I could not verify live current chart hits for {understanding.genre_hint or 'this style'}, "
                f"but these source-grounded representative picks are concrete starting points: {names}."
            )
        elif music_routing.recommendation_plan.question_type == "trending_tracks":
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
    if use_chinese:
        if understanding.intent == "label_recommendation":
            answer = f"针对 {understanding.genre_hint or '这种风格'}，我找到的主要厂牌候选是 {names}。"
        elif understanding.intent == "artist_recommendation":
            answer = f"针对 {understanding.genre_hint or '这种风格'}，我找到的主要艺人候选是 {names}。"
        elif understanding.intent == "track_recommendation":
            answer = f"针对 {understanding.genre_hint or '这种风格'}，我找到的主要曲目候选是 {names}。"
        else:
            answer = f"我找到的相关音乐实体包括 {names}。"

        details: list[str] = []
        for entity in entities[:4]:
            related = ", ".join(item.name for item in entity.related_entities[:4])
            sources = ", ".join(entity.sources[:3]) or "可信证据"
            detail = f"{entity.name} 由 {sources} 支持"
            if related:
                detail += f"；相关艺人或实体包括 {related}"
            details.append(detail + "。")
        return answer + " " + " ".join(details)

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
    max_tokens: int | None = None,
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
    if max_tokens:
        payload["max_tokens"] = max_tokens

    log_memory("before_llm_call", model=config.model, max_tokens=max_tokens or 0)
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

    log_memory("after_llm_call", response_bytes=len(raw))
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
    max_answer_tokens: int | None = None,
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
        max_tokens=max_answer_tokens,
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
    should_use_structured_music = False
    if music_routing and (music_routing.ranked_entities or music_routing.recommendation_plan.candidate_tracks):
        should_use_structured_music = _looks_like_unhelpful_answer(answer) or _answer_omits_recommendation_candidates(
            answer,
            music_routing,
        )
    if music_routing and _has_album_cards(music_routing):
        should_use_structured_music = should_use_structured_music or _looks_like_unhelpful_answer(answer)
    if music_routing and _answer_omits_artist_track_cards(answer, music_routing):
        should_use_structured_music = True

    if music_routing and should_use_structured_music:
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
