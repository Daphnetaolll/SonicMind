# SonicMind Pricing And Usage Plan

This document describes the current MVP pricing, usage, and plan-feature system. Creator and Pro subscriptions are integrated with Stripe Checkout + Billing when backend Stripe env vars are configured; extra-pack purchases remain placeholders.

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

Extra credits are used only after the user's plan quota is exhausted. In this MVP, credits are represented by local `credit_transactions` rows; real extra-pack purchases are not available yet.

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

Stripe customer/subscription/payment identifiers are stored through the existing `subscriptions` and `billing_events` tables.

## Frontend Behavior

- `/pricing` is public.
- `/chat` is protected and redirects logged-out users to `/login`.
- Chat displays current plan, remaining quota, extra credits, and answer certainty.
- Sources, settings, saved history, and favorites are foldable so the page stays compact.
- Free users can start Creator or Pro Stripe Checkout when billing env vars are configured.
- Creator users can upgrade directly to Pro through `POST /api/billing/subscription-plan`.
- General billing management, cancellation, payment methods, invoices, and downgrades open Stripe Customer Portal.
- Extra-pack buttons show a Coming Soon modal.
- Spotify recommendations appear only when the backend marks the question as music-related.

## Backend Enforcement

The backend plan config lives in `backend/config/plans.py`. `src/services/quota_service.py` evaluates:

- Free daily usage against a UTC day window.
- Creator/Pro usage against Stripe webhook-backed subscription periods in production.
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

## Stripe Subscription Integration

The first Stripe version covers only monthly Creator and Pro subscriptions:

1. Backend Checkout Session endpoint creates Stripe-hosted subscription checkout.
2. Checkout success redirect returns to `/pricing?checkout=success` and does not grant access directly.
3. Verified Stripe webhooks insert idempotent `billing_events`.
4. Stripe subscription events upsert `subscriptions` by `provider_subscription_id`.
5. Verified subscription periods update `users.plan`, `subscription_status`, and billing period dates.
6. Production quota falls back to Free when no current Stripe-backed subscription row exists.
7. Direct Creator to Pro upgrades replace the current Stripe subscription item price and then sync account status.

Detailed setup is in [STRIPE_BILLING.md](STRIPE_BILLING.md).

## Future Billing Steps

1. Add extra-pack one-time Checkout Sessions.
2. Create credit transactions only after verified extra-pack payment events.
3. Tighten FIFO credit consumption for purchased packs.
4. Add deeper cancellation, failed-payment, downgrade, and renewal tests.

## Remaining Risks

- Monthly demo periods are rolling 30-day local periods only outside production.
- Extra-credit usage does not yet perform full FIFO expiration accounting.
- Saved history and favorites are intentionally simple lists.
- Direct Creator to Pro upgrades can return a provider error if Stripe requires additional payment authentication.
- Browser automation covers the main production register/login/chat journey; billing-specific browser flows still need a dedicated Stripe test-mode suite.
