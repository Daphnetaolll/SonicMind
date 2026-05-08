from __future__ import annotations

from src.memory import ChatTurn, rewrite_query_with_history


def test_rewrite_artist_pronoun_followup_to_recent_artist() -> None:
    # Artist pronouns should resolve before retrieval and Spotify routing run.
    rewritten, changed = rewrite_query_with_history(
        "recommand me his popular album",
        [ChatTurn(user="who is ISOxo", assistant="ISOxo is a San Diego-based producer and DJ.")],
    )

    assert changed is True
    assert rewritten == "recommand me ISOxo's popular album"
