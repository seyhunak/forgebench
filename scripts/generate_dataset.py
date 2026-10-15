#!/usr/bin/env python3
"""Generate the synthetic ``finance_v1`` dataset deterministically.

Ground truth comes from explicit construction rules, never from a model.
The same seed always produces byte-identical files, which is what makes the
dataset versionable and results reproducible.

Scenario families and their ground-truth rules
---------------------------------------------
matched               amounts, dates and references all agree
amount_mismatch       amounts differ (even if other fields also differ)
date_mismatch         dates differ, amounts agree
reference_mismatch    references differ, amounts agree
duplicate             one side shows more occurrences than the other
ambiguous             conflicting weak signals a rule engine cannot resolve;
                      ground truth is "escalate to a human"

Precedence when several signals fire (documented, applied by both the
generator and the mock provider): duplicate > amount > reference > date.

Usage:
    python scripts/generate_dataset.py --seed 42 --train 100 --dev 40 --test 60
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from forgebench.schemas import BenchmarkCase, Category  # noqa: E402

DATASET_NAME = "finance_v1"
DATASET_VERSION = "1.0.0"
CREATED_ON = "2026-10-15"

VENDORS = [
    "Acme Supplies Ltd",
    "Northwind Freight",
    "Blue Peak Consulting",
    "Harbor Point Logistics",
    "Cedar & Finch LLP",
    "Silverline Media",
    "Granite Software Inc",
    "Tidewater Foods",
    "Lantern Health Group",
    "Redwood Office Furniture",
    "Kestrel Analytics",
    "Bright Path Training",
    "Ironbridge Metals",
    "Sable Print House",
    "Juniper Facilities",
    "Orchard Street Cafe",
    "Vantage Legal Services",
    "Copperfield Electronics",
    "Meadowlark Cleaning",
    "Pinnacle Systems BV",
]

CENTS = [".00", ".00", ".50", ".99", ".37", ".15", ".80"]


def business_days(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


DAYS = business_days(date(2026, 8, 17), date(2026, 10, 30))


def money(rng: random.Random) -> Decimal:
    whole = rng.choice([rng.randint(1, 950), rng.randint(1, 250), rng.randint(500, 9500)])
    return Decimal(f"{whole}{rng.choice(CENTS)}")


def fmt_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def shift_day(day: date, delta: int) -> date:
    shifted = day + timedelta(days=delta)
    while shifted.weekday() >= 5:  # keep landed dates on business days
        shifted += timedelta(days=1 if delta >= 0 else -1)
    return shifted


def typo_digit(rng: random.Random, text: str) -> str:
    """Change one digit of ``text`` to a different digit."""
    digits = [i for i, ch in enumerate(text) if ch.isdigit() and ch != "0"]
    position = rng.choice(digits)
    new_digit = rng.choice([d for d in "123456789" if d != text[position]])
    return text[:position] + new_digit + text[position + 1 :]


def base_fields(rng: random.Random) -> dict[str, str]:
    vendor = rng.choice(VENDORS)
    amount = money(rng)
    invoice = f"INV-{rng.randint(1000, 9999)}"
    day = rng.choice(DAYS)
    return {
        "vendor": vendor,
        "description": f"Invoice payment - {vendor}",
        "bank_amount": fmt_amount(amount),
        "ledger_amount": fmt_amount(amount),
        "bank_reference": invoice,
        "ledger_reference": invoice,
        "bank_date": day.isoformat(),
        "ledger_date": day.isoformat(),
    }


def case_matched(rng: random.Random) -> dict:
    fields = base_fields(rng)
    if rng.random() < 0.12:  # refund-shaped edge case: negative, still matched
        fields["bank_amount"] = fmt_amount(-Decimal(fields["bank_amount"]))
        fields["ledger_amount"] = fields["bank_amount"]
    return {
        "input": fields,
        "explanation": "Bank and ledger agree on amount, date and reference.",
    }


def case_amount_mismatch(rng: random.Random, index: int) -> dict:
    fields = base_fields(rng)
    ledger = Decimal(fields["ledger_amount"])
    variant = index % 4
    if variant == 0:  # digit typo
        bank = Decimal(typo_digit(rng, fields["ledger_amount"]))
    elif variant == 1:  # double payment on the bank side
        bank = ledger * 2
    elif variant == 2:  # fee deducted by the bank
        bank = ledger - Decimal(str(rng.choice(["2.50", "5.00", "12.75"])))
    else:  # partial payment
        bank = (ledger / 2).quantize(Decimal("0.01"))
    fields["bank_amount"] = fmt_amount(bank)
    note = ""
    if rng.random() < 0.3:  # mixed signal: another field also differs; amount wins
        fields["ledger_reference"] = fields["ledger_reference"] + "-A"
        note = " Reference differs as well; amount precedence applies."
    return {
        "input": fields,
        "explanation": f"Bank amount {fields['bank_amount']} does not equal ledger amount "
        f"{fields['ledger_amount']}.{note}",
    }


def case_date_mismatch(rng: random.Random) -> dict:
    fields = base_fields(rng)
    ledger_day = date.fromisoformat(fields["ledger_date"])
    fields["bank_date"] = shift_day(ledger_day, rng.choice([1, 1, 2, 3, 5])).isoformat()
    return {
        "input": fields,
        "explanation": f"Bank date {fields['bank_date']} does not equal ledger date "
        f"{fields['ledger_date']}; amounts agree.",
    }


def case_reference_mismatch(rng: random.Random, index: int) -> dict:
    fields = base_fields(rng)
    reference = fields["ledger_reference"]
    variant = index % 4
    if variant == 0:
        fields["bank_reference"] = f"{reference}-A"
    elif variant == 1:
        fields["bank_reference"] = typo_digit(rng, reference)
    elif variant == 2:
        fields["bank_reference"] = reference.replace("INV", "INVOICE")
    else:
        fields["bank_reference"] = reference.lower()
    bank_ref = fields["bank_reference"]
    return {
        "input": fields,
        "explanation": f"Bank reference '{bank_ref}' does not equal ledger reference "
        f"'{reference}'; amounts agree.",
    }


def case_duplicate(rng: random.Random) -> dict:
    fields = base_fields(rng)
    fields["bank_occurrences"] = "2"
    fields["ledger_occurrences"] = "1"
    return {
        "input": fields,
        "explanation": "The bank shows the transaction twice while the ledger shows it once.",
    }


def case_ambiguous(rng: random.Random, index: int) -> dict:
    fields = base_fields(rng)
    if index % 2 == 0:
        # A one-character reference difference plus a one-day date shift:
        # typo-and-correction or a genuinely different invoice? Undecidable
        # from the row alone.
        fields["bank_reference"] = typo_digit(rng, fields["ledger_reference"])
        fields["bank_date"] = shift_day(date.fromisoformat(fields["ledger_date"]), 1).isoformat()
        explanation = (
            "Reference differs by one character and the bank posted one day later; "
            "could be a corrected typo or a separate invoice. Human review required."
        )
    else:
        # The same pair appears twice on both sides: duplicate payment, or two
        # legitimate orders with identical terms?
        fields["bank_occurrences"] = "2"
        fields["ledger_occurrences"] = "2"
        explanation = (
            "The transaction pair appears twice on both sides; duplicates or two "
            "legitimate orders with identical terms cannot be told apart here."
        )
    return {"input": fields, "explanation": explanation}


BUILDERS = {
    "matched": lambda rng, i: case_matched(rng),
    "amount_mismatch": case_amount_mismatch,
    "date_mismatch": lambda rng, i: case_date_mismatch(rng),
    "reference_mismatch": case_reference_mismatch,
    "duplicate": lambda rng, i: case_duplicate(rng),
    "ambiguous": case_ambiguous,
}

#: Family counts per split. Sums to the requested split sizes at generation time.
_SPLIT_RATIOS = {
    "train": {
        "matched": 0.25,
        "amount_mismatch": 0.20,
        "date_mismatch": 0.15,
        "reference_mismatch": 0.15,
        "duplicate": 0.12,
        "ambiguous": 0.13,
    },
    "dev": {
        "matched": 0.25,
        "amount_mismatch": 0.20,
        "date_mismatch": 0.15,
        "reference_mismatch": 0.15,
        "duplicate": 0.125,
        "ambiguous": 0.125,
    },
    "test": {
        "matched": 0.25,
        "amount_mismatch": 0.20,
        "date_mismatch": 0.1667,
        "reference_mismatch": 0.1667,
        "duplicate": 0.10,
        "ambiguous": 0.1166,
    },
}


def rule_precedence(fields: dict[str, str]) -> Category:
    """The documented deterministic rules, duplicated here as a generation check."""
    bank_occ, ledger_occ = fields.get("bank_occurrences"), fields.get("ledger_occurrences")
    if bank_occ is not None and ledger_occ is not None and bank_occ != ledger_occ:
        return Category.DUPLICATE
    if Decimal(fields["bank_amount"]) != Decimal(fields["ledger_amount"]):
        return Category.AMOUNT_MISMATCH
    if fields["bank_reference"].strip() != fields["ledger_reference"].strip():
        return Category.REFERENCE_MISMATCH
    if fields["bank_date"] != fields["ledger_date"]:
        return Category.DATE_MISMATCH
    return Category.MATCHED


def build_split(split: str, size: int, rng: random.Random) -> list[dict]:
    ratios = _SPLIT_RATIOS[split]
    counts = {family: round(ratio * size) for family, ratio in ratios.items()}
    # Fix rounding drift onto the largest family so the split hits `size` exactly.
    drift = size - sum(counts.values())
    if drift:
        biggest = max(counts, key=lambda family: counts[family])
        counts[biggest] += drift

    cases: list[dict] = []
    for family, count in counts.items():
        for index in range(count):
            record = BUILDERS[family](rng, index)
            fields = record["input"]
            explanation = record["explanation"]
            if family == "ambiguous":
                category = Category.AMBIGUOUS
            else:
                category = rule_precedence(fields)
                expected = {
                    "matched": Category.MATCHED,
                    "amount_mismatch": Category.AMOUNT_MISMATCH,
                    "date_mismatch": Category.DATE_MISMATCH,
                    "reference_mismatch": Category.REFERENCE_MISMATCH,
                    "duplicate": Category.DUPLICATE,
                }[family]
                if category is not expected:
                    raise SystemExit(
                        f"generator bug: family {family} produced rule classification "
                        f"{category.value} for {fields['bank_reference']}"
                    )
            cases.append(
                {
                    "family": family,
                    "category": category,
                    "input": fields,
                    "explanation": explanation,
                }
            )
    rng.shuffle(cases)
    return cases


def to_case(record: dict, case_id: str) -> BenchmarkCase:
    category: Category = record["category"]
    return BenchmarkCase.model_validate(
        {
            "id": case_id,
            "task": "exception_classification",
            "input": record["input"],
            "expected": {
                "category": category.value,
                "requires_review": category is not Category.MATCHED,
            },
            "scenario_family": record["family"],
            "reference_explanation": record["explanation"],
        }
    )


def write_card(out_dir: Path, split_sizes: dict[str, int], distribution: dict[str, int]) -> None:
    total = sum(split_sizes.values())
    lines = [
        "# Dataset card: finance_v1",
        "",
        f"- **Name:** {DATASET_NAME}  ",
        f"- **Version:** {DATASET_VERSION}  ",
        "- **Task:** transaction exception classification and reconciliation triage  ",
        f"- **Created:** {CREATED_ON} (fully synthetic; no customer data)  ",
        f"- **Total cases:** {total}  ",
        "- **License:** Apache-2.0 (synthetic data generated by this repository)",
        "",
        "## What is in it",
        "",
        "Each case shows one bank line item next to its ledger counterpart and asks:",
        "do these match, and if not, what kind of exception is it? Ground truth is",
        "produced by the deterministic rules in `scripts/generate_dataset.py`, never",
        "by a model.",
        "",
        "| Family | Ground truth |",
        "| --- | --- |",
        "| matched | amounts, dates and references agree |",
        "| amount_mismatch | amounts differ (takes precedence when other fields also differ) |",
        "| date_mismatch | dates differ, amounts agree |",
        "| reference_mismatch | references differ, amounts agree |",
        "| duplicate | one side shows more occurrences than the other |",
        "| ambiguous | conflicting weak signals; must be escalated to a human |",
        "",
        "## Splits",
        "",
        "| Split | Cases |",
        "| --- | ---: |",
    ]
    lines += [f"| {split} | {size} |" for split, size in split_sizes.items()]
    lines += [
        "",
        "## Class distribution (all splits)",
        "",
        "| Category | Cases |",
        "| --- | ---: |",
    ]
    lines += [f"| {category} | {count} |" for category, count in sorted(distribution.items())]
    lines += [
        "",
        "## Intended use",
        "",
        "- Comparing prompts, structured-output strategies, and (later) customized",
        "  models on one fixed, versioned test set.",
        "- Validating an evaluation pipeline end to end without any API key.",
        "",
        "## Out-of-scope uses and limitations",
        "",
        "- The data is synthetic. It does not encode real banking messiness",
        "  (partial payments with remittance advice, multi-currency rounding,",
        "  jurisdiction rules) and strong results here do not imply production",
        "  readiness.",
        "- 'ambiguous' encodes one specific kind of undecidability. Real operations",
        "  contain more. Treat escalation metrics as a lower bound.",
        "- Do not use this dataset to compare models that were trained on it.",
        "  The train split exists for prompt examples and adaptation experiments;",
        "  the test split is the only reporting surface.",
        "",
        "## Regeneration",
        "",
        "```bash",
        "python scripts/generate_dataset.py --seed 42 --train 100 --dev 40 --test 60",
        "```",
        "",
        "The command is deterministic: same seed, byte-identical files.",
    ]
    (out_dir / "dataset_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=int, default=100)
    parser.add_argument("--dev", type=int, default=40)
    parser.add_argument("--test", type=int, default=60)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "datasets" / DATASET_NAME)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    split_sizes = {"train": args.train, "dev": args.dev, "test": args.test}
    distribution: dict[str, int] = {}
    next_id = 1
    for split, size in split_sizes.items():
        records = build_split(split, size, rng)
        lines = []
        for record in records:
            case = to_case(record, f"FIN-{next_id:04d}")
            next_id += 1
            distribution[case.expected.category.value] = (
                distribution.get(case.expected.category.value, 0) + 1
            )
            lines.append(case.model_dump_json())
        (out_dir / f"{split}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {out_dir / f'{split}.jsonl'} ({len(records)} cases)")

    meta = {
        "name": DATASET_NAME,
        "version": DATASET_VERSION,
        "task": "exception_classification",
        "license": "Apache-2.0 (synthetic data generated by this repository)",
        "created_on": CREATED_ON,
        "families": list(BUILDERS),
        "splits": {
            split: {"file": f"{split}.jsonl", "n": size} for split, size in split_sizes.items()
        },
        "generator": {
            "script": "scripts/generate_dataset.py",
            "seed": args.seed,
            "note": "Ground truth from deterministic rules; no model involved.",
        },
    }
    (out_dir / "dataset.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    write_card(out_dir, split_sizes, distribution)
    print(f"wrote {out_dir / 'dataset.json'} and dataset_card.md")
    print(f"class distribution: {json.dumps(dict(sorted(distribution.items())))}")


if __name__ == "__main__":
    main()
