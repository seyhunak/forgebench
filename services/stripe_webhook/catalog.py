"""Stripe credit catalog: the product grid of theForgeBench credit model.

1 credit = $0.10. A benchmark run costs a flat 30 credits ($3.00); a
custom-task run costs 1 credit ($0.10) per case — metering lives in the
local ledger (``src/forgebench/credits.py``). The dataset pack is also
priced in credits so it can be bought with the same wallet.

Prices and the pack sizes are set here in one place; payment-link URLs
and Stripe price IDs come from the environment, never from this file.
"""

from __future__ import annotations

USDCENT = 0.10  # USD per credit

PACKAGES: dict[str, dict[str, str | int]] = {
    "starter_50": {"label": "Starter", "credits": 50},  # $5.00
    "growth_100": {"label": "Growth", "credits": 100},  # $10.00
    "scale_250": {"label": "Scale", "credits": 250},  # $25.00
    "max_500": {"label": "Max", "credits": 500},  # $50.00
}

UNLIMITED: dict[str, str | int] = {
    "label": "Enterprise Unlimited",
    "unlimited": True,
}  # $5,000 one-time

# Dataset pack: also paid from the credit wallet (adjust inside the file
# whenever the pack size changes).
DATASET_PACK: dict[str, str | int] = {
    "label": "Domain dataset pack",
    "credits": 250,  # $25.00
}


def package_prices() -> dict[str, dict[str, str]]:
    """Catalog as served on ``GET /packages``."""
    out: dict[str, dict[str, str]] = {}
    for name, pkg in PACKAGES.items():
        credits = int(pkg["credits"])
        out[name] = {
            "label": str(pkg["label"]),
            "credits": str(credits),
            "usd": f"{credits * USDCENT:.2f}",
            "price_per_credit": f"{USDCENT:.2f}",
        }
    out["enterprise_unlimited"] = {
        "label": str(UNLIMITED["label"]),
        "credits": "unlimited",
        "usd": "5000.00",
        "price_per_credit": "-",
    }
    out["dataset_pack"] = {
        "label": str(DATASET_PACK["label"]),
        "credits": str(DATASET_PACK["credits"]),
        "usd": f"{int(DATASET_PACK['credits']) * USDCENT:.2f}",
        "price_per_credit": f"{USDCENT:.2f}",
    }
    return out


def grant_for_package(name: str) -> dict[str, str | int | bool] | None:
    """The redeemable grant for a purchased catalog name."""
    if name in PACKAGES:
        pkg = PACKAGES[name]
        return {
            "package": name,
            "label": str(pkg["label"]),
            "credits": int(pkg["credits"]),
            "unlimited": False,
            "dataset_pack": False,
        }
    if name == "enterprise_unlimited":
        return {
            "package": name,
            "label": str(UNLIMITED["label"]),
            "credits": 0,
            "unlimited": True,
            "dataset_pack": True,
        }
    if name == "dataset_pack":
        return {
            "package": name,
            "label": str(DATASET_PACK["label"]),
            "credits": 0,
            "unlimited": False,
            "dataset_pack": True,
        }
    return None
