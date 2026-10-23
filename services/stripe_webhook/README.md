# ForgeBench Stripe credit service

The monetization backend: a single small FastAPI process on `:8583` that
turns Stripe checkout events into single-use voucher codes and redeems
them into the local ForgeBench credit ledger.

```
Stripe Checkout ──webhook──▶ services/stripe_webhook ──voucher email/log──▶ customer
                                                                                │
forgebench redeem FB-… ──────POST /redeem────────────────────────────────────────┘
        │
        ▼
.forgebench/credits.json   (local balance; git-ignored)
```

## The model
- **1 credit = $0.10. Every benchmark or task run = 1 credit** (runs are
  counted in `src/forgebench/credits.py`).
- Packs: **Starter 50 / $5 · Growth 100 / $10 · Scale 250 / $25 · Max 500 / $50**
- **Domain dataset pack: 250 credits / $25** — same wallet.
- **Enterprise Unlimited: $5,000 one-time.**

## Operation (devctl)
```bash
devctl up forgebench-stripe        # webhook service on :8583
devctl up forgebench-stripe-listen # Stripe CLI sandbox forwarder (test mode)
devctl status | grep stripe
devctl logs forgebench-stripe      # webhook traffic + vouchers
```
Falls back to `make stripe` (same process, foreground). The service
loads the repo-root `.env` at startup, so STRIPE_*( secrets live there —
not in `devctl.json`.

## Sandbox wiring (verified end-to-end, 2026-10-23)

Test-mode account `acct_1Q5YYN2mqUSt5owq` via the Stripe CLI:

1. Six products + one-time prices ($5/$10/$25/$50/$25/$5000) and payment
   links with checkout metadata `package=<catalog name>`. The created
   link URLs live in `.env` as `STRIPE_LINK_<PACKAGE>` and are rendered
   as **Buy** buttons on the dashboard's 08 · Credits → Top-up table.
2. `devctl` service `forgebench-stripe-listen` runs
   `stripe listen --all-snapshot --forward-to 127.0.0.1:8583/stripe/webhook`
   so sandbox events reach the local webhook; its signing secret
   (`whsec_…`) is in `.env` as `STRIPE_WEBHOOK_SECRET`.
3. Verified loop: `stripe trigger checkout.session.completed \
   --add "checkout_session:metadata[package]=scale_250"` → webhook
   verified the Stripe signature → minted `FB-SCALE_250-…` into
   `.forgebench/vouchers.json` → `.venv/bin/forgebench redeem <code>`
   credited 250 credits into `.forgebench/credits.json` and burned the
   voucher.
   `stripe trigger` fixtures carry no metadata, which is exactly why
   `STRIPE_PRICE_MAP` exists as the safety net.

## Production

Point a public HTTPS endpoint (Dashboard webhook or tunnel) at
`/stripe/webhook`, put its signing secret in `.env`, swap the `test_`
payment links for live ones, and set `STRIPE_SECRET_KEY` so
metadata-less sessions resolve via line items.

## Stripe configuration (one-time)

1. **Products & prices** — create one-time prices in Stripe for:
   `starter_50 ($5)`, `growth_100 ($10)`, `scale_250 ($25)`, `max_500
   ($50)`, `dataset_pack ($25)`, `enterprise_unlimited ($5000)`.
2. **Payment links** for each product. In every link, set checkout
   metadata **`package` = the catalog name** (`starter_50`, …,
   `enterprise_unlimited`, `dataset_pack`) — that metadata is the
   primary fulfillment path. Export each URL as `STRIPE_LINK_<PACKAGE>`
   in `.env`; `GET /packages` turns them into the dashboard's Buy
   buttons.
3. **Webhook** —
   - sandbox: the `forgebench-stripe-listen` devctl service (Stripe CLI
     forwards test events).
   - production: a Dashboard endpoint at
     `https://<public-host>:8583/stripe/webhook` with event
     `checkout.session.completed`; copy its signing secret.
4. **Env for the service** (`.env` at repo root is loaded at startup) —
   - `STRIPE_WEBHOOK_SECRET` — required; without it `/stripe/webhook`
     answers 503 and accepts nothing.
   - `STRIPE_PRICE_MAP` — `price_A=starter_50,…` fallback when a
     checkout session ships without metadata.
   - `STRIPE_SECRET_KEY` — optional: lets the service fetch line items
     for metadata-less checkouts.
   - `SMTP_HOST/PORT/USER/PASSWORD/FROM` — optional email fulfillment;
     without it the voucher is logged for manual delivery.

## Ledger
Voucher ledger: `.forgebench/vouchers.json` (override:
`STRIPE_LEDGER_PATH`). Customer balance: `.forgebench/credits.json`
(override: `FORGEBENCH_CREDITS_PATH`). Both are git-ignored. Ledger
mode for the harness: `FORGEBENCH_CREDITS_MODE=off|observe|enforce`
(`off` is the MVP default — community use is never blocked).
