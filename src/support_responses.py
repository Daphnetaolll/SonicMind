from __future__ import annotations


def get_support_answer(query: str) -> str | None:
    """
    Return small SonicMind-owned answers for product/support/safety prompts.
    These questions should not be routed into general web music retrieval, where
    terms like "pricing" or "password" can accidentally become Spotify support answers.
    """
    lowered = query.lower()
    if any(marker in lowered for marker in ("home address", "private information", "private info", "address of", "地址")):
        return (
            "I can’t help find or reveal a private person’s home address or unsupported personal information. "
            "I can still help with public music history, releases, genres, labels, or safely sourced artist context."
        )

    if any(marker in lowered for marker in ("pricing", "price", "plans", "plan", "free", "subscription", "upgrade")) and (
        "sonicmind" in lowered or "your" in lowered or "app" in lowered or "pricing" in lowered
    ):
        return (
            "SonicMind currently has three placeholder plans: Free is $0/month with 5 questions per UTC day, "
            "Student / Creator is $4.99/month with 200 questions per month, and Pro is $8.99/month with "
            "1000 questions per month. Extra packs are planned at $2.99 for 50 questions and $4.99 for "
            "100 questions, but payment is not integrated yet."
        )

    if any(marker in lowered for marker in ("log in", "login", "reset my password", "password reset", "sign in", "help me log")):
        return (
            "Use the SonicMind login page to sign in with your local test account. Password reset email is not "
            "implemented in this portfolio build yet, so create a new local account or use the documented seed "
            "accounts while testing."
        )

    return None
