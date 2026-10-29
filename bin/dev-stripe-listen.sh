#!/usr/bin/env bash
# Stripe CLI sandbox forwarder -> forgebench-stripe webhook (test mode).
#
# Runs under devctl (launchd), which executes `exec <cmd>` from the repo root
# with a bare PATH, so this follows the same shape as the other dev-stripe.sh
# scripts: resolve the repo root from THIS script's location, source .env, and
# drive the listener with --api-key so the account cannot drift from the one
# that charges.
#
# WHY --api-key AND NOT THE CLI LOGIN: `stripe listen` with no key forwards
# events for whatever account `stripe login` last left behind. That can be a
# DIFFERENT account from the one STRIPE_SECRET_KEY charges, and the mismatch is
# silent: Stripe takes the payment, redirects to /console?topup=success, and
# the event for that payment is never forwarded -- so no credit is ever written
# and the only trace is a console showing "success" over an unchanged balance.
# Driving the listener from the same key that charges makes both the SAME
# account by construction, so they cannot drift again.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR/.."

# Secrets live in .env (gitignored), never in devctl.json (committed).
# shellcheck disable=SC1091
set -a; . ./.env; set +a

# The Stripe CLI's default profile has no key (only `seyhunak` does), so a bare
# `stripe listen` exits immediately with "You have not configured API keys
# yet" and launchd respawns it forever. Pull the test key from the CLI config
# when .env doesn't supply one -- the webhook route verifies signatures with
# STRIPE_WEBHOOK_SECRET, which is independent of which account the listener
# uses, so this is safe as long as the forward target is right.
if [ -z "${STRIPE_SECRET_KEY:-}" ] && [ -f ~/.config/stripe/config.toml ]; then
  STRIPE_SECRET_KEY="$(awk -F"'" '/test_mode_api_key/{print $2; exit}' ~/.config/stripe/config.toml)"
fi
: "${STRIPE_SECRET_KEY:?STRIPE_SECRET_KEY missing: set it in .env or run stripe login}"

exec stripe listen \
  --api-key "$STRIPE_SECRET_KEY" \
  --all-snapshot \
  --forward-to 127.0.0.1:8583/stripe/webhook