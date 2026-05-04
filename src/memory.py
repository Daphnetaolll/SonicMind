from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatTurn:
    user: str
    assistant: str


def normalize_chat_history(chat_history: list[Any] | None, max_turns: int = 3) -> list[ChatTurn]:
    if not chat_history:
        return []

    turns: list[ChatTurn] = []
    for item in chat_history:
        if isinstance(item, ChatTurn):
            turns.append(item)
            continue

        if isinstance(item, dict):
            user = str(item.get("user", "")).strip()
            assistant = str(item.get("assistant", "")).strip()
            if user or assistant:
                turns.append(ChatTurn(user=user, assistant=assistant))

    if max_turns <= 0:
        return []
    return turns[-max_turns:]


def format_chat_history(turns: list[ChatTurn]) -> str:
    if not turns:
        return ""

    lines: list[str] = []
    for idx, turn in enumerate(turns, start=1):
        lines.append(f"[Conversation {idx}] User: {turn.user}")
        lines.append(f"[Conversation {idx}] Assistant: {turn.assistant}")
    return "\n".join(lines)


def append_chat_turn(chat_history: list[ChatTurn], query: str, answer: str, max_turns: int = 3) -> list[ChatTurn]:
    updated = list(chat_history)
    updated.append(ChatTurn(user=query, assistant=answer))
    if max_turns <= 0:
        return []
    return updated[-max_turns:]


def has_coreference(query: str) -> bool:
    lowered = query.lower()
    markers = ("it", "this", "that", "they", "them", "their", "its")
    phrases = (
        "this genre",
        "that genre",
        "this style",
        "that style",
        "this music",
        "that music",
    )
    return any(phrase in lowered for phrase in phrases) or any(marker in lowered.split() for marker in markers)


def extract_recent_topic(chat_history: list[ChatTurn]) -> str | None:
    if not chat_history:
        return None

    patterns = [
        r"what is\s+([A-Za-z][A-Za-z0-9&+\- ]{1,40})",
        r"tell me about\s+([A-Za-z][A-Za-z0-9&+\- ]{1,40})",
        r"explain\s+([A-Za-z][A-Za-z0-9&+\- ]{1,40})",
        r"\b([A-Za-z][A-Za-z0-9&+\- ]{1,40}\s+music)\b",
    ]

    for turn in reversed(chat_history):
        text = turn.user.strip()
        for pattern in patterns:
            # Prefer the actual subject of the prior question, not the whole question text.
            match = re.search(pattern, text, flags=re.I)
            if match:
                topic = match.group(1).strip("\"' ,.!?:;")
                if topic:
                    return topic
    return None


def rewrite_query_with_history(query: str, chat_history: list[ChatTurn]) -> tuple[str, bool]:
    if not has_coreference(query):
        return query, False

    topic = extract_recent_topic(chat_history)
    if not topic:
        return query, False

    rewritten = query
    replacements: list[tuple[str, str]] = [
        (r"\bthis genre\b", topic),
        (r"\bthat genre\b", topic),
        (r"\bthis style\b", topic),
        (r"\bthat style\b", topic),
        (r"\bthis music\b", topic),
        (r"\bthat music\b", topic),
        (r"\bit\b", topic),
        (r"\bits\b", f"{topic}'s"),
        (r"\btheir\b", f"{topic}'s"),
    ]
    for pattern, value in replacements:
        # Word-boundary replacements keep short pronouns from corrupting surrounding words.
        rewritten = re.sub(pattern, value, rewritten, flags=re.I)

    rewritten = re.sub(r"\s+", " ", rewritten).strip()
    return rewritten or query, rewritten != query
