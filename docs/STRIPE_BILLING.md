# Stripe Billing Integration

This project now supports Stripe Checkout + Billing for Creator and Pro monthly subscriptions.
Extra packs are intentionally not implemented in this first billing version.

## What The App Implements

- `POST /api/billing/checkout-session`
  - Authenticated route.
  - Accepts `creator` or `pro`.
  - Creates a Stripe Checkout subscription session.
  - Returns a Stripe-hosted redirect URL.
  - Does not grant paid access.
- `POST /api/billing/portal-session`
  - Authenticated route.
  - Opens Stripe Customer Portal for a linked Stripe customer.
  - Used for payment methods, invoices, cancellation, and subscription management.
- `POST /api/billing/webhook`
  - Public route authenticated by Stripe signature verification.
  - Reads the raw request body and `Stripe-Signature` header.
  - Processes Stripe events into `billing_events`, `subscriptions`, and `users`.

Webhook reconciliation is the only source of truth for paid access. Checkout success redirects only show a processing state in the React app until `/api/me` reflects the webhook-applied plan.

## Required Backend Environment Variables

Set these on the backend service only. Never add them to frontend `VITE_*` variables.

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CREATOR_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
FRONTEND_BASE_URL=https://your-frontend-domain.example
SONICMIND_ENABLE_DEMO_BILLING_ROLLOVER=false
```

Important: `STRIPE_CREATOR_PRICE_ID` and `STRIPE_PRO_PRICE_ID` must be Stripe **Price** ids that start with `price_`. Stripe product ids start with `prod_` and will fail checkout configuration validation.

## Stripe Dashboard Test Mode Steps

1. Open Stripe Dashboard in test mode.
2. Create a product for Creator and add a recurring monthly USD price of `$4.99`.
3. Create a product for Pro and add a recurring monthly USD price of `$8.99`.
4. Copy the recurring price ids, not product ids.
5. Configure Customer Portal in test mode:
   - Allow updating payment methods.
   - Allow viewing invoice history.
   - Allow cancellation.
   - Optionally allow subscription updates between Creator and Pro.
6. Create a webhook endpoint:
   - Local Stripe CLI: forward to `http://127.0.0.1:8000/api/billing/webhook`.
   - Render/live test service: `https://your-api-domain.example/api/billing/webhook`.
7. Subscribe the endpoint to these events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
8. Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`.

## Local Test Mode Flow

Run the backend and frontend with test-mode Stripe env vars:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev
```

In another terminal, forward Stripe webhooks:

```bash
stripe listen --forward-to 127.0.0.1:8000/api/billing/webhook
```

Use Stripe test cards in Checkout. After returning to `/pricing?checkout=success`, the frontend polls `/api/me` until the webhook updates the user plan.

## Render Deployment

Backend service:

- Add the Stripe env vars above.
- Keep `SONICMIND_ENABLE_DEMO_BILLING_ROLLOVER=false`.
- Redeploy after setting env vars.
- Confirm the webhook endpoint is the deployed API URL plus `/api/billing/webhook`.

Frontend service:

- Keep only browser-safe values such as `VITE_API_BASE_URL`.
- Do not add Stripe secret keys or webhook secrets.

## Live Mode Cutover

1. Complete Stripe account activation, identity, bank, and tax/business profile.
2. Recreate or confirm live-mode Creator and Pro recurring prices.
3. Replace test `sk_test_`, `whsec_`, and `price_` values with live-mode values.
4. Create a live-mode webhook endpoint for the production API URL.
5. Run a small live payment with a real card.
6. Confirm `/api/me` shows the paid plan only after the webhook event is processed.
7. Confirm Customer Portal can cancel and that cancellation removes paid access after Stripe sends the relevant subscription event.

## Operational Notes

- `billing_events.provider_event_id` is unique and makes webhook retries idempotent.
- `subscriptions.provider_subscription_id` is unique per provider and is upserted by Stripe subscription events.
- Production quota requires a current Stripe-backed subscription row for paid access.
- Local demo paid-plan rollover remains available only outside production for seeded test users.
