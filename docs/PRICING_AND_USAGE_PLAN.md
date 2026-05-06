# SonicMind Pricing And Usage Plan

This document describes the current MVP pricing, usage, and plan-feature system. It is intentionally payment-provider-free: Stripe is not integrated yet, and all upgrade / buy buttons are placeholders.

## Plan Table

| Plan | Price | Usage Limit | Answer Tokens | RAG Top-K | Spotify Limit | History | Favorites | Playlist Style |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Free | $0/month | 5 questions/day, UTC reset | 400 | 3 | 5 | Temporary frontend session only | No | No |
| Student / Creator | $4.99/month | 200 questions/month | 800 | 5 | 10 | Saved until user deletes it | Yes | No |
| Pro | $8.99/month | 1000 questions/month | 1200 | 8 | 15 | Saved until user deletes it | Yes | Yes |

## Extra Credits

| Pack | Price | Credits | Expiration |
| --- | --- | --- | --- |
| Extra 50 | $2.99 | 50 questions | 12 months |
| Extra 100 | $4.99 | 100 questions | 12 months |

Extra credits are used only after the user's plan quota is exhausted. In this MVP, credits are represented by local `credit_transactions` rows; real purchases are not available yet.

## Usage Rules

- Users must be logged in before asking questions.
- The backend checks quota before RAG, LLM, or Spotify calls.
- A question costs 1 credit only after the text answer succeeds.
- If the text answer fails, usage is not deducted.
- If the text answer succeeds but Spotify fails, usage is deducted and the UI shows `Spotify recommendation temporarily unavailable.`
- Refreshing the page, loading history, and viewing favorites do not deduct usage.
- Regenerating an answer is treated as a new question and deducts usage if the answer succeeds.
- Frontend counters are display-only; the backend is the source of truth.

## Data Model

The MVP extends the existing PostgreSQL schema instead of introducing a heavy billing system:

- `users`: stores `plan`, `subscription_status`, billing period dates, and a denormalized extra-credit snapshot.
- `question_logs`: records question lifecycle and whether the answer was charged.
- `usage_ledger`: records append-only usage events such as `free_usage`, `subscription_usage`, and `extra_credit_usage`.
- `credit_transactions`: stores extra-credit grants and usage adjustments.
- `chat_messages`: stores saved history for Creator and Pro users.
- `favorite_tracks`: stores paid-plan favorite tracks with Spotify metadata.

The preferred future billing model can keep these tables and add Stripe customer/subscription/payment identifiers through the existing `subscriptions` and `billing_events` tables.

## Frontend Behavior

- `/pricing` is public.
- `/chat` is protected and redirects logged-out users to `/login`.
- Chat displays current plan, remaining quota, extra credits, and answer certainty.
- Sources, settings, saved history, and favorites are foldable so the page stays compact.
- Upgrade and extra-pack buttons show a Coming Soon modal.
- Spotify recommendations appear only when the backend marks the question as music-related.

## Backend Enforcement

The backend plan config lives in `backend/config/plans.py`. `src/services/quota_service.py` evaluates:

- Free daily usage against a UTC day window.
- Creator/Pro usage against the stored billing period.
- Extra credits after plan quota is exhausted.
- Plan-specific RAG Top-K, max answer tokens, and Spotify card limits.

## Local Seed Users

Set these variables and run the seed script:

```bash
SONICMIND_ENABLE_DEV_SEEDS=true
SONICMIND_DEV_SEED_PASSWORD=Test123456!
python3 scripts/seed_plan_test_users.py
```

Seeded users:

- `freetest@example.com` on Free
- `creatortest@example.com` on Student / Creator
- `protest@example.com` on Pro

## Future Stripe Integration Steps

1. Add Stripe product and price ids for Creator, Pro, and extra packs.
2. Create backend checkout-session endpoints.
3. Store Stripe customer and subscription ids in `subscriptions`.
4. Process Stripe webhooks into `billing_events`.
5. Update `users.plan`, `subscription_status`, and billing period dates from verified webhooks only.
6. Create credit transactions only after verified extra-pack payment events.
7. Add cancellation, failed-payment, and renewal tests.

## Remaining Risks

- Monthly periods are rolling 30-day local periods until Stripe supplies real billing-cycle dates.
- Extra-credit usage does not yet perform full FIFO expiration accounting.
- Saved history and favorites are intentionally simple lists.
- The frontend has a build check, but no browser automation coverage for the new modal flows yet.
