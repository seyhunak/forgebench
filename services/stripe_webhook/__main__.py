"""Allow ``python -m services.stripe_webhook`` (devctl command)."""

from services.stripe_webhook.app import main

main()
