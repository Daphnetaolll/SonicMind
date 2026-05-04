from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from src.rag_pipeline import answer_question
from src.services.admin_service import is_admin
from src.services.auth_service import authenticate_user, get_user, register_user
from src.services.question_service import (
    mark_question_failed,
    mark_question_succeeded,
    start_question,
)
from src.services.quota_service import get_quota_status, record_successful_question_usage
from src.services.subscription_service import activate_monthly_subscription, get_subscription_status


ROOT_DIR = Path(__file__).resolve().parent
RAW_DIR = ROOT_DIR / "data" / "raw"
CHUNKS_PATH = ROOT_DIR / "data" / "processed" / "chunks.jsonl"
META_PATH = ROOT_DIR / "data" / "processed" / "chunk_meta.jsonl"
INDEX_PATH = ROOT_DIR / "data" / "index" / "faiss.index"


def init_session_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("current_user_id", None)
    st.session_state.setdefault("question_success_message", None)


def safe_error_message(exc: Exception, *, fallback: str) -> str:
    message = str(exc)
    lowered = message.lower()

    # Keep provider, SQL, and stack-level details out of the UI while still giving users a next step.
    if "llm request failed" in lowered or "missing llm_api_key" in lowered or "openai_api_key" in lowered:
        return "The answer service is unavailable right now. Check the LLM configuration and try again."
    if "search api failed" in lowered or "tavily" in lowered or "brave" in lowered:
        return "External search is unavailable right now. Please try again in a moment."
    if "spotify" in lowered:
        return "Spotify results could not be loaded right now. The answer may still be available."
    if "database" in lowered or "psycopg" in lowered or "postgres" in lowered:
        return "Account or quota storage is unavailable right now. Please try again shortly."
    return fallback


def save_uploaded_files(uploaded_files: list[st.runtime.uploaded_file_manager.UploadedFile]) -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for uploaded in uploaded_files:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in {".txt", ".md"}:
            raise ValueError(f"Unsupported file type: {uploaded.name}. Only .txt and .md are allowed.")

        target = RAW_DIR / Path(uploaded.name).name
        target.write_bytes(uploaded.getbuffer())
        saved_paths.append(target)

    return saved_paths


def rebuild_knowledge_base() -> None:
    commands = [
        [sys.executable, "scripts/preprocess.py"],
        [sys.executable, "scripts/embed_corpus.py"],
        [sys.executable, "scripts/build_index.py"],
    ]

    for cmd in commands:
        result = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )


def knowledge_base_ready() -> bool:
    return CHUNKS_PATH.exists() and META_PATH.exists() and INDEX_PATH.exists()


def count_local_source_docs() -> int:
    if not RAW_DIR.exists():
        return 0
    return len(list(RAW_DIR.glob("*.txt"))) + len(list(RAW_DIR.glob("*.md")))


def logout() -> None:
    st.session_state.current_user_id = None
    st.session_state.chat_history = []
    st.session_state.last_result = None
    st.session_state.question_success_message = None
    st.rerun()


def get_current_user():
    user_id = st.session_state.current_user_id
    if not user_id:
        return None
    user = get_user(user_id)
    if not user:
        st.session_state.current_user_id = None
        return None
    return user


def render_auth_panel() -> None:
    current_user = get_current_user()
    st.header("Account")

    if current_user:
        quota = get_quota_status(current_user.id)
        subscription = get_subscription_status(current_user.id)
        st.success(f"Signed in as {current_user.email}")
        st.caption(f"Remaining questions: {quota.remaining}")
        if quota.charge_type == "subscription":
            st.caption("Plan: Monthly subscription")
            if subscription.current_period_end:
                st.caption(f"Renews on: {subscription.current_period_end:%Y-%m-%d}")
        elif quota.charge_type == "free":
            st.caption("Plan: Free trial")
        else:
            st.caption("Plan: No active quota")

        if st.button("Sign Out", use_container_width=True):
            logout()
        return

    sign_in_tab, register_tab = st.tabs(["Sign In", "Register"])

    with sign_in_tab:
        with st.form("sign_in_form", clear_on_submit=False):
            email = st.text_input("Email", key="sign_in_email")
            password = st.text_input("Password", type="password", key="sign_in_password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                # Validate empty credentials before hitting the database so the auth form feels intentional.
                if not email.strip() or not password:
                    st.error("Email and password are required.")
                elif not (user := authenticate_user(email, password)):
                    st.error("Invalid email or password.")
                else:
                    st.session_state.current_user_id = user.id
                    st.session_state.chat_history = []
                    st.session_state.last_result = None
                    st.session_state.question_success_message = None
                    st.rerun()

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            display_name = st.text_input("Display name (optional)", key="register_display_name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            confirm_password = st.text_input("Confirm password", type="password", key="register_confirm_password")
            submitted = st.form_submit_button("Create Account", use_container_width=True)
            if submitted:
                if not email.strip() or not password:
                    st.error("Email and password are required.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    try:
                        user = register_user(email, password, display_name=display_name or None)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.current_user_id = user.id
                        st.session_state.chat_history = []
                        st.session_state.last_result = None
                        st.session_state.question_success_message = None
                        st.rerun()


def render_subscription_panel(current_user) -> None:
    st.subheader("3. Subscription")
    if not current_user:
        st.info("Sign in to view subscription options.")
        return

    quota = get_quota_status(current_user.id)
    subscription = get_subscription_status(current_user.id)

    if subscription.subscribed:
        st.success(f"{subscription.plan_name} is active.")
        st.caption(f"Remaining monthly questions: {subscription.remaining}")
        if subscription.current_period_end:
            st.caption(f"Current period ends: {subscription.current_period_end:%Y-%m-%d}")
        st.caption("Auto-renew is enabled.")
        return

    if quota.allowed:
        st.info("You are still using your free trial. A monthly plan becomes available after the free quota is exhausted.")
        return

    st.warning("Your free trial is exhausted.")
    st.markdown("**Monthly Plan**")
    st.caption("100 questions every 30 days with automatic renewal.")
    st.caption("Payment gateway integration is still pending, so this button activates the local subscription flow only.")

    if st.button("Start Monthly Subscription", use_container_width=True):
        try:
            subscription = activate_monthly_subscription(current_user.id)
        except Exception as exc:  # pragma: no cover - UI surface
            st.error(str(exc))
        else:
            st.success(f"{subscription.plan_name} activated.")
            st.rerun()


def render_history() -> None:
    if not st.session_state.chat_history:
        st.info("No chat history yet. Ask a question to get started.")
        return

    st.subheader("Chat History")
    for idx, turn in enumerate(st.session_state.chat_history, start=1):
        with st.container():
            st.markdown(f"**Turn {idx}**")
            st.markdown(f"**User:** {turn['user']}")
            st.markdown(f"**Assistant:** {turn['assistant']}")


def render_references() -> None:
    result = st.session_state.last_result
    if not result:
        return

    st.subheader("Sources")
    if result.query_rewritten:
        st.caption(f"Retrieval query: {result.retrieval_query}")
    st.caption(f"Route: {' -> '.join(result.route_steps)}")
    st.caption(
        f"Local sufficiency: {result.local_assessment.label} | Final sufficiency: {result.final_assessment.label}"
    )

    for idx, doc in enumerate(result.used_evidence, start=1):
        label = (
            f"#{idx} | {doc.source_type.upper()} | {doc.title} | "
            f"score={doc.retrieval_score:.4f}"
        )
        with st.expander(label):
            st.write(doc.full_text)
            st.caption(f"Source type: {doc.source_type}")
            st.caption(f"Source name: {doc.source_name}")
            st.caption(f"Trust: {doc.trust_level}")
            if doc.metadata.get("purpose"):
                st.caption(f"Source role: {doc.metadata['purpose']}")
            if doc.metadata.get("access_mode"):
                st.caption(f"Access mode: {doc.metadata['access_mode']}")
            if doc.url:
                st.markdown(f"[Open source]({doc.url})")


def render_music_module() -> None:
    result = st.session_state.last_result
    if not result:
        return

    understanding = result.query_understanding
    st.subheader("Understanding")
    st.caption(f"Intent: `{understanding.intent}`")
    st.caption(f"Primary entity type: `{understanding.primary_entity_type}`")
    if understanding.genre_hint:
        st.caption(f"Genre: `{understanding.genre_hint}`")
    st.caption(f"Spotify target: `{understanding.spotify_display_target}`")
    plan = result.music_routing.recommendation_plan
    if plan.question_type != "none":
        st.caption(f"Recommendation plan: `{plan.question_type}` | confidence: `{plan.confidence}`")
        if plan.uncertainty_note:
            st.caption(f"Recommendation note: {plan.uncertainty_note}")

    st.subheader("Recommended Results")
    if not result.ranked_entities:
        st.caption("No ranked music entities were extracted for this question.")
    for entity in result.ranked_entities[:6]:
        st.markdown(f"**{entity.name}**")
        st.caption(f"{entity.type} | score={entity.score:.2f}")
        if entity.genres:
            st.caption("Genres: " + ", ".join(entity.genres[:3]))
        if entity.sources:
            st.caption("Sources: " + ", ".join(entity.sources[:3]))
        related = [item.name for item in entity.related_entities[:4]]
        if related:
            st.caption("Related: " + ", ".join(related))

    st.subheader("Spotify Matches")
    if result.spotify_cards:
        for card in result.spotify_cards[:6]:
            st.markdown(f"**{card.title}**")
            st.caption(f"{card.card_type} | {card.subtitle}")
            if card.source_entity:
                st.caption(f"From: {card.source_entity}")
            recommendation_source = card.metadata.get("recommendation_source")
            if recommendation_source in {"curated", "generated", "web_search", "evidence", "spotify_fallback"}:
                target = (
                    f"{card.metadata.get('recommendation_artist', '')} - "
                    f"{card.metadata.get('recommendation_title', '')}"
                ).strip(" -")
                source_label = recommendation_source.replace("_", " ").title()
                st.caption(f"{source_label} target: {target}")
                if card.metadata.get("recommendation_sources"):
                    st.caption(f"Recommendation sources: {card.metadata['recommendation_sources']}")
            if card.popularity is not None:
                st.caption(f"Popularity: {card.popularity}")
            if card.embed_url:
                height = 152 if card.card_type == "track" else 180
                # Streamlit deprecated components.v1.iframe; st.iframe keeps Spotify embeds forward-compatible.
                st.iframe(card.embed_url, height=height)
            else:
                st.markdown(f"[Open in Spotify]({card.spotify_url})")
    elif result.music_routing.spotify_error:
        st.warning(result.music_routing.spotify_error)
        if understanding.genre_hint:
            st.markdown(
                f"[Open Spotify search for {understanding.genre_hint}]"
                f"(https://open.spotify.com/search/{quote(understanding.genre_hint)})"
            )
    elif understanding.needs_spotify:
        st.info("No Spotify matches were found for the resolved music entities.")
        if understanding.genre_hint:
            st.markdown(
                f"[Open Spotify search for {understanding.genre_hint}]"
                f"(https://open.spotify.com/search/{quote(understanding.genre_hint)})"
            )
    else:
        st.caption("Spotify display was not needed for this question.")

    st.caption(
        "Spotify is used only to display playable matches. "
        "Recommendation choices come from trusted evidence, curated data, or generated trusted-source discoveries."
    )


def main() -> None:
    st.set_page_config(page_title="RAG Music Guide", layout="wide")
    init_session_state()
    current_user = get_current_user()

    st.title("RAG Music Guide")
    st.caption("Ask questions with a hybrid RAG flow: local knowledge base first, then trusted sites, then web search when needed.")

    with st.sidebar:
        render_auth_panel()
        st.divider()
        st.header("Settings")
        topk = st.slider("Context chunks (Top-K)", min_value=1, max_value=6, value=3)
        max_history_turns = st.slider("Conversation turns to keep", min_value=1, max_value=5, value=3)
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.last_result = None
            st.session_state.question_success_message = None
            st.rerun()

    # Give the knowledge-base/subscription column enough width to avoid broken word wrapping with the sidebar open.
    upload_col, chat_col = st.columns([1.2, 1.8], gap="large")

    with upload_col:
        st.subheader("1. Knowledge Base")
        local_docs = count_local_source_docs()
        if knowledge_base_ready():
            st.success(f"Knowledge base ready. Detected {local_docs} local source documents.")
        else:
            st.warning("No usable knowledge base was detected. Upload documents and rebuild the corpus first.")

        if not current_user:
            st.info("Sign in to use the app. Knowledge-base uploads are restricted to administrators.")
        elif not is_admin(current_user.id):
            st.info("Knowledge-base uploads are restricted to administrators.")
        else:
            st.caption("Upload new txt / md files here, then rebuild the knowledge base.")
            uploaded_files = st.file_uploader(
                "Select txt / md files to add to the knowledge base",
                type=["txt", "md"],
                accept_multiple_files=True,
            )

            if st.button("Save and Rebuild Knowledge Base", use_container_width=True):
                if not uploaded_files:
                    st.warning("Select at least one file first.")
                else:
                    try:
                        saved_paths = save_uploaded_files(uploaded_files)
                        with st.spinner("Rebuilding the knowledge base. This may take a moment..."):
                            rebuild_knowledge_base()
                        st.success("Knowledge base updated.")
                        st.write("Saved files:")
                        for path in saved_paths:
                            st.write(f"- {path.name}")
                    except Exception as exc:  # pragma: no cover - UI surface
                        st.error(safe_error_message(exc, fallback="The knowledge base could not be rebuilt."))

        st.divider()
        render_subscription_panel(current_user)

    with chat_col:
        st.subheader("2. Ask")
        question = st.text_input("Enter a question", placeholder="For example: What is house music?")
        quota = get_quota_status(current_user.id) if current_user else None
        if current_user and quota:
            st.caption(f"Remaining questions: {quota.remaining}")

        hide_result_this_run = False
        if st.button("Ask Question", type="primary", use_container_width=True):
            # Hide stale answers while validating or processing a new submission.
            hide_result_this_run = True
            st.session_state.question_success_message = None
            if not current_user:
                st.warning("Sign in or create an account before asking questions.")
            elif not question.strip():
                st.warning("Enter a question first.")
            elif not knowledge_base_ready():
                st.warning("No usable knowledge base is available. Upload documents and rebuild the corpus first.")
            elif not quota or not quota.allowed:
                st.warning("You have no remaining questions in your current quota. Start a subscription to continue.")
            else:
                question_log_id = start_question(current_user.id, question.strip())
                try:
                    st.session_state.last_result = None
                    st.session_state.question_success_message = None
                    with st.spinner("Retrieving context and generating an answer..."):
                        result = answer_question(
                            question.strip(),
                            chat_history=st.session_state.chat_history,
                            topk=topk,
                            max_history_turns=max_history_turns,
                        )
                    charge_type = quota.charge_type
                    remaining_quota = record_successful_question_usage(
                        user_id=current_user.id,
                        question_log_id=question_log_id,
                    )
                    mark_question_succeeded(
                        question_log_id,
                        result.answer,
                        charge_type=charge_type,
                    )
                    st.session_state.chat_history = [
                        {"user": turn.user, "assistant": turn.assistant}
                        for turn in result.updated_chat_history
                    ]
                    st.session_state.last_result = result
                    # Rerun after charging so all quota counters render from the same fresh database state.
                    st.session_state.question_success_message = (
                        f"Remaining questions after this answer: {remaining_quota.remaining}"
                    )
                    st.rerun()
                except Exception as exc:  # pragma: no cover - UI surface
                    mark_question_failed(question_log_id, str(exc))
                    st.error(safe_error_message(exc, fallback="The question could not be answered right now."))

        if st.session_state.question_success_message and not hide_result_this_run:
            # Render post-answer quota feedback only after validation so stale success text does not survive errors.
            st.caption(st.session_state.question_success_message)

        if st.session_state.last_result and not hide_result_this_run:
            # Keep the answer column dominant so diagnostics do not wrap into unreadable fragments.
            answer_col, spotify_col = st.columns([2.5, 1], gap="large")
            with answer_col:
                st.subheader("Answer")
                st.write(st.session_state.last_result.answer)
                st.caption(f"Certainty: {st.session_state.last_result.certainty}")
                if st.session_state.last_result.uncertainty_note:
                    st.info(st.session_state.last_result.uncertainty_note)
                if st.session_state.last_result.citations:
                    refs = ", ".join(
                        f"[{citation.number}] {citation.source_name}"
                        for citation in st.session_state.last_result.citations
                    )
                    st.caption(f"Citations: {refs}")
                render_references()
            with spotify_col:
                render_music_module()

    st.divider()
    render_history()


if __name__ == "__main__":
    main()
