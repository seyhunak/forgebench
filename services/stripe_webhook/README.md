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
devctl up forgebench-stripe       # start on :8583
devctl status | grep stripe
devctl logs forgebench-stripe     # webhook traffic + vouchers
```
Falls back to `make stripe` (same process, foreground).

## Stripe configuration (one-time)

1. **Products & prices** — create one-time prices in Stripe for:
   `starter_50 ($5)`, `growth_100 ($10)`, `scale_250 ($25)`, `max_500
   ($50)`, `dataset_pack ($25)`, `enterprise_unlimited ($5000)`.
2. **Payment links** for each product. In every link, set checkout
   metadata **`package` = the catalog name** (`starter_50`, …,
   `enterprise_unlimited`, `dataset_pack`) — that metadata is the
   primary fulfillment path.
3. **Endpoints** —
   `STRIPE_LINK_STARTER_50=https://buy.stripe.com/…` (env) are exported
   on `GET /packages` so the README can render buy buttons.
4. **Webhook** — add an endpoint pointing at this service
   (`https://<public-host>:8583/stripe/webhook`; a tail/cloudflared
   tunnel for local dev), event set = `checkout.session.completed`,
   and copy the signing secret.
5. **Env for the service** (`.env`, `devctl.json` env, or launchd) —
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
