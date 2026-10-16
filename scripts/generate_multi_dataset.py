#!/usr/bin/env python3
"""Generate additional synthetic datasets: legal_v1, insurance_v1, support_v1.

Each dataset uses the same input field names as finance_v1
(bank_amount, ledger_amount, bank_reference, ledger_reference,
bank_date, ledger_date) so ForgeBench can run them without code changes.
Run with: python scripts/generate_multi_dataset.py
"""

import json
import random
from pathlib import Path

SEED = 2026
FAMILIES = ["matched", "amount_mismatch", "date_mismatch", "reference_mismatch", "duplicate", "ambiguous"]

random.seed(SEED)


def make_case(prefix, idx, family, category, requires_review, input_fields, expected_fields, explanation):
    return {
        "id": f"{prefix}-{idx:04d}",
        "task": "classification",
        "input": input_fields,
        "expected": expected_fields,
        "scenario_family": family,
        "notes": None,
        "reference_explanation": explanation,
    }


def write_jsonl(path, cases):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")


def write_dataset(name, version, task, license_str, train, dev, test, card_md):
    d = Path("datasets") / name
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "task": task,
        "license": license_str,
        "created_on": "2026-10-16",
        "families": FAMILIES,
        "splits": {
            "train": {"file": "train.jsonl", "n": len(train)},
            "dev": {"file": "dev.jsonl", "n": len(dev)},
            "test": {"file": "test.jsonl", "n": len(test)},
        },
        "generator": {
            "script": "scripts/generate_multi_dataset.py",
            "seed": SEED,
            "note": "Ground truth from deterministic rules; no model involved.",
        },
    }
    (d / "dataset.json").write_text(json.dumps(manifest, indent=2))
    (d / "dataset_card.md").write_text(card_md)
    write_jsonl(d / "train.jsonl", train)
    write_jsonl(d / "dev.jsonl", dev)
    write_jsonl(d / "test.jsonl", test)
    print(f"✓ {name}: train={len(train)}, dev={len(dev)}, test={len(test)}, "
          f"total={len(train)+len(dev)+len(test)}")


# ---------------- legal_v1 ----------------
vendors_legal = [
    "Skadden Arps", "Kirkland Ellis", "Latham Watkins", "Baker McKenzie",
    "Dentons", "Clifford Chance", "Linklaters", "White & Case",
    "Jones Day", "Morgan Lewis", "Sidley Austin", "Gibson Dunn",
]
clauses = ["nda", "service_agreement", "lease", "procurement", "consulting"]


def legal_case(idx, family, category, vendor, clause_type, contract_val,
               invoice_val, contract_ref, invoice_ref, contract_date,
               invoice_date, requires_review, explanation):
    return make_case("LG", idx, family, category, requires_review,
        {
            "vendor": vendor,
            "description": f"Clause review - {clause_type} - {vendor}",
            "bank_amount": contract_val,
            "ledger_amount": invoice_val,
            "bank_reference": contract_ref,
            "ledger_reference": invoice_ref,
            "bank_date": contract_date,
            "ledger_date": invoice_date,
        },
        {"category": category, "requires_review": requires_review},
        explanation,
    )


cases_legal = []
idx = 1
for _ in range(30):  # matched
    v = random.choice(vendors_legal)
    amt = f"${random.randint(1000, 50000)}"
    ref = f"CTR-{random.randint(10000, 99999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(legal_case(idx, "matched", "matched", v, random.choice(clauses),
                                  amt, amt, ref, ref, date, date, False,
                                  "Contract and invoice agree on amount, date and reference."))
    idx += 1
for _ in range(20):  # amount mismatch
    v = random.choice(vendors_legal)
    a = f"${random.randint(1000, 30000)}"
    b = f"${random.randint(1000, 30000)}"
    while b == a:
        b = f"${random.randint(1000, 30000)}"
    ref = f"CTR-{random.randint(10000, 99999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(legal_case(idx, "amount_mismatch", "amount_mismatch", v, random.choice(clauses),
                                  a, b, ref, ref, date, date, True,
                                  f"Contract amount {a} does not equal invoice amount {b}."))
    idx += 1
for _ in range(15):  # date mismatch
    v = random.choice(vendors_legal)
    amt = f"${random.randint(1000, 30000)}"
    ref = f"CTR-{random.randint(10000, 99999)}"
    d1 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    while d2 == d1:
        d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(legal_case(idx, "date_mismatch", "date_mismatch", v, random.choice(clauses),
                                  amt, amt, ref, ref, d1, d2, True,
                                  f"Contract date {d1} does not equal invoice date {d2}; amounts agree."))
    idx += 1
for _ in range(15):  # reference mismatch
    v = random.choice(vendors_legal)
    amt = f"${random.randint(1000, 30000)}"
    r1 = f"CTR-{random.randint(10000, 99999)}"
    r2 = f"CTR-{random.randint(10000, 99999)}-A"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(legal_case(idx, "reference_mismatch", "reference_mismatch", v, random.choice(clauses),
                                  amt, amt, r1, r2, date, date, True,
                                  f"Contract reference {r1} does not equal invoice reference {r2}; amounts agree."))
    idx += 1
for _ in range(12):  # duplicate
    v = random.choice(vendors_legal)
    amt = f"${random.randint(1000, 30000)}"
    ref = f"CTR-{random.randint(10000, 99999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(make_case("LG", idx, "duplicate", "duplicate", True,
        {"vendor": v, "description": f"Clause review - {random.choice(clauses)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": ref, "ledger_reference": ref,
         "bank_date": date, "ledger_date": date},
        {"category": "duplicate", "requires_review": True},
        "The contract shows the clause twice while the invoice shows it once."))
    idx += 1
for _ in range(13):  # ambiguous
    v = random.choice(vendors_legal)
    amt = f"${random.randint(1000, 30000)}"
    r1 = f"CTR-{random.randint(10000, 99999)}"
    r2 = f"CTR-{random.randint(10000, 99999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_legal.append(make_case("LG", idx, "ambiguous", "ambiguous", True,
        {"vendor": v, "description": f"Clause review - {random.choice(clauses)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": r1, "ledger_reference": r2,
         "bank_date": date, "ledger_date": date},
        {"category": "ambiguous", "requires_review": True},
        "Reference and date both differ weakly; human review required."))
    idx += 1

random.shuffle(cases_legal)
legal_card = """# Dataset card: legal_v1

- **Name:** legal_v1
- **Version:** 1.0.0
- **Task:** contract clause reconciliation and exception triage
- **Created:** 2026-10-16 (fully synthetic; no client data)
- **Total cases:** 105
- **License:** Apache-2.0 (synthetic data generated by this repository)

## What is in it

Each case shows one contract clause next to its invoice counterpart and asks:
do these match, and if not, what kind of exception is it? Ground truth is produced
by deterministic rules, never by a model.

| Family | Ground truth |
| --- | --- |
| matched | amounts, dates and references agree |
| amount_mismatch | contract amount differs from invoice amount |
| date_mismatch | dates differ, amounts agree |
| reference_mismatch | contract reference differs from invoice reference |
| duplicate | one side shows more occurrences than the other |
| ambiguous | conflicting weak signals; must be escalated to a human |

## Splits

| Split | Cases |
| --- | ---: |
| train | 42 |
| dev | 21 |
| test | 42 |

## Intended use

- Comparing prompts and structured-output strategies on legal document data.
- Validating an evaluation pipeline end to end without any API key.
"""
write_dataset("legal_v1", "1.0.0", "claims_reconciliation",
              "Apache-2.0 (synthetic data generated by this repository)",
              cases_legal[:42], cases_legal[42:63], cases_legal[63:], legal_card)

# ---------------- insurance_v1 ----------------
vendors_ins = [
    "Allstate", "State Farm", "Liberty Mutual", "Travelers", "USAA",
    "Nationwide", "Progressive", "Chubb", "AIG", "Hartford",
]
claim_types = ["auto", "property", "liability", "workers_comp", "health"]


def insurance_case(idx, family, category, vendor, claim_type,
                   adjuster_val, paid_val, claim_ref, paid_ref,
                   adj_date, paid_date, requires_review, explanation):
    return make_case("IN", idx, family, category, requires_review,
        {
            "vendor": vendor,
            "description": f"Claim - {claim_type} - {vendor}",
            "bank_amount": adjuster_val,
            "ledger_amount": paid_val,
            "bank_reference": claim_ref,
            "ledger_reference": paid_ref,
            "bank_date": adj_date,
            "ledger_date": paid_date,
        },
        {"category": category, "requires_review": requires_review},
        explanation,
    )


cases_ins = []
idx = 1
for _ in range(30):  # matched
    v = random.choice(vendors_ins)
    amt = f"${random.randint(500, 20000)}"
    ref = f"CLM-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(insurance_case(idx, "matched", "matched", v, random.choice(claim_types),
                                    amt, amt, ref, ref, date, date, False,
                                    "Adjuster and payment agree on amount, date and reference."))
    idx += 1
for _ in range(20):  # amount mismatch
    v = random.choice(vendors_ins)
    a = f"${random.randint(500, 15000)}"
    b = f"${random.randint(500, 15000)}"
    while b == a:
        b = f"${random.randint(500, 15000)}"
    ref = f"CLM-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(insurance_case(idx, "amount_mismatch", "amount_mismatch", v, random.choice(claim_types),
                                    a, b, ref, ref, date, date, True,
                                    f"Adjuster amount {a} does not equal paid amount {b}."))
    idx += 1
for _ in range(15):  # date mismatch
    v = random.choice(vendors_ins)
    amt = f"${random.randint(500, 15000)}"
    ref = f"CLM-{random.randint(100000, 999999)}"
    d1 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    while d2 == d1:
        d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(insurance_case(idx, "date_mismatch", "date_mismatch", v, random.choice(claim_types),
                                    amt, amt, ref, ref, d1, d2, True,
                                    f"Adjuster date {d1} does not equal paid date {d2}; amounts agree."))
    idx += 1
for _ in range(15):  # reference mismatch
    v = random.choice(vendors_ins)
    amt = f"${random.randint(500, 15000)}"
    r1 = f"CLM-{random.randint(100000, 999999)}"
    r2 = f"CLM-{random.randint(100000, 999999)}-A"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(insurance_case(idx, "reference_mismatch", "reference_mismatch", v, random.choice(claim_types),
                                    amt, amt, r1, r2, date, date, True,
                                    f"Adjuster reference {r1} does not equal paid reference {r2}; amounts agree."))
    idx += 1
for _ in range(12):  # duplicate
    v = random.choice(vendors_ins)
    amt = f"${random.randint(500, 15000)}"
    ref = f"CLM-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(make_case("IN", idx, "duplicate", "duplicate", True,
        {"vendor": v, "description": f"Claim - {random.choice(claim_types)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": ref, "ledger_reference": ref,
         "bank_date": date, "ledger_date": date},
        {"category": "duplicate", "requires_review": True},
        "The adjuster shows the claim twice while the payment shows it once."))
    idx += 1
for _ in range(13):  # ambiguous
    v = random.choice(vendors_ins)
    amt = f"${random.randint(500, 15000)}"
    r1 = f"CLM-{random.randint(100000, 999999)}"
    r2 = f"CLM-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_ins.append(make_case("IN", idx, "ambiguous", "ambiguous", True,
        {"vendor": v, "description": f"Claim - {random.choice(claim_types)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": r1, "ledger_reference": r2,
         "bank_date": date, "ledger_date": date},
        {"category": "ambiguous", "requires_review": True},
        "Reference and date both differ weakly; human review required."))
    idx += 1

random.shuffle(cases_ins)
ins_card = """# Dataset card: insurance_v1

- **Name:** insurance_v1
- **Version:** 1.0.0
- **Task:** insurance claims adjudication and exception triage
- **Created:** 2026-10-16 (fully synthetic; no claimant data)
- **Total cases:** 105
- **License:** Apache-2.0 (synthetic data generated by this repository)

## What is in it

Each case shows one insurance adjuster assessment next to its payment record and asks:
do these match, and if not, what kind of exception is it? Ground truth is produced
by deterministic rules, never by a model.

| Family | Ground truth |
| --- | --- |
| matched | amounts, dates and references agree |
| amount_mismatch | adjuster amount differs from paid amount |
| date_mismatch | dates differ, amounts agree |
| reference_mismatch | adjuster reference differs from paid reference |
| duplicate | one side shows more occurrences than the other |
| ambiguous | conflicting weak signals; must be escalated to a human |

## Splits

| Split | Cases |
| --- | ---: |
| train | 42 |
| dev | 21 |
| test | 42 |

## Intended use

- Comparing prompts and structured-output strategies on insurance claims data.
- Validating an evaluation pipeline end to end without any API key.
"""
write_dataset("insurance_v1", "1.0.0", "claims_reconciliation",
              "Apache-2.0 (synthetic data generated by this repository)",
              cases_ins[:42], cases_ins[42:63], cases_ins[63:], ins_card)

# ---------------- support_v1 ----------------
vendors_sup = [
    "Zendesk", "Freshdesk", "Intercom", "Salesforce Service Cloud", "HubSpot",
    "ServiceNow", "Freshservice", "Jira Service Management", "Kustomer", "Gorgias",
]
ticket_types = ["billing", "technical", "account_access", "feature_request", "refund"]


def support_case(idx, family, category, vendor, ticket_type,
                 agent_val, system_val, ticket_ref, system_ref,
                 agent_date, system_date, requires_review, explanation):
    return make_case("SP", idx, family, category, requires_review,
        {
            "vendor": vendor,
            "description": f"Ticket - {ticket_type} - {vendor}",
            "bank_amount": agent_val,
            "ledger_amount": system_val,
            "bank_reference": ticket_ref,
            "ledger_reference": system_ref,
            "bank_date": agent_date,
            "ledger_date": system_date,
        },
        {"category": category, "requires_review": requires_review},
        explanation,
    )


cases_sup = []
idx = 1
for _ in range(30):  # matched
    v = random.choice(vendors_sup)
    amt = f"${random.randint(10, 5000)}"
    ref = f"TKT-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(support_case(idx, "matched", "matched", v, random.choice(ticket_types),
                                  amt, amt, ref, ref, date, date, False,
                                  "Agent resolution and system record agree."))
    idx += 1
for _ in range(20):  # amount mismatch
    v = random.choice(vendors_sup)
    a = f"${random.randint(10, 3000)}"
    b = f"${random.randint(10, 3000)}"
    while b == a:
        b = f"${random.randint(10, 3000)}"
    ref = f"TKT-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(support_case(idx, "amount_mismatch", "amount_mismatch", v, random.choice(ticket_types),
                                  a, b, ref, ref, date, date, True,
                                  f"Agent amount {a} does not equal system amount {b}."))
    idx += 1
for _ in range(15):  # date mismatch
    v = random.choice(vendors_sup)
    amt = f"${random.randint(10, 3000)}"
    ref = f"TKT-{random.randint(100000, 999999)}"
    d1 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    while d2 == d1:
        d2 = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(support_case(idx, "date_mismatch", "date_mismatch", v, random.choice(ticket_types),
                                  amt, amt, ref, ref, d1, d2, True,
                                  f"Agent date {d1} does not equal system date {d2}; amounts agree."))
    idx += 1
for _ in range(15):  # reference mismatch
    v = random.choice(vendors_sup)
    amt = f"${random.randint(10, 3000)}"
    r1 = f"TKT-{random.randint(100000, 999999)}"
    r2 = f"TKT-{random.randint(100000, 999999)}-A"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(support_case(idx, "reference_mismatch", "reference_mismatch", v, random.choice(ticket_types),
                                  amt, amt, r1, r2, date, date, True,
                                  f"Agent reference {r1} does not equal system reference {r2}; amounts agree."))
    idx += 1
for _ in range(12):  # duplicate
    v = random.choice(vendors_sup)
    amt = f"${random.randint(10, 3000)}"
    ref = f"TKT-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(make_case("SP", idx, "duplicate", "duplicate", True,
        {"vendor": v, "description": f"Ticket - {random.choice(ticket_types)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": ref, "ledger_reference": ref,
         "bank_date": date, "ledger_date": date},
        {"category": "duplicate", "requires_review": True},
        "The agent shows the ticket twice while the system shows it once."))
    idx += 1
for _ in range(13):  # ambiguous
    v = random.choice(vendors_sup)
    amt = f"${random.randint(10, 3000)}"
    r1 = f"TKT-{random.randint(100000, 999999)}"
    r2 = f"TKT-{random.randint(100000, 999999)}"
    date = f"2026-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    cases_sup.append(make_case("SP", idx, "ambiguous", "ambiguous", True,
        {"vendor": v, "description": f"Ticket - {random.choice(ticket_types)} - {v}",
         "bank_amount": amt, "ledger_amount": amt,
         "bank_reference": r1, "ledger_reference": r2,
         "bank_date": date, "ledger_date": date},
        {"category": "ambiguous", "requires_review": True},
        "Reference and date both differ weakly; human review required."))
    idx += 1

random.shuffle(cases_sup)
sup_card = """# Dataset card: support_v1

- **Name:** support_v1
- **Version:** 1.0.0
- **Task:** customer support ticket triage and exception reconciliation
- **Created:** 2026-10-16 (fully synthetic; no customer data)
- **Total cases:** 105
- **License:** Apache-2.0 (synthetic data generated by this repository)

## What is in it

Each case shows one support agent resolution next to its system record and asks:
do these match, and if not, what kind of exception is it? Ground truth is produced
by deterministic rules, never by a model.

| Family | Ground truth |
| --- | --- |
| matched | amounts, dates and references agree |
| amount_mismatch | agent amount differs from system amount |
| date_mismatch | dates differ, amounts agree |
| reference_mismatch | agent reference differs from system reference |
| duplicate | one side shows more occurrences than the other |
| ambiguous | conflicting weak signals; must be escalated to a human |

## Splits

| Split | Cases |
| --- | ---: |
| train | 42 |
| dev | 21 |
| test | 42 |

## Intended use

- Comparing prompts and structured-output strategies on support ticket data.
- Validating an evaluation pipeline end to end without any API key.
"""
write_dataset("support_v1", "1.0.0", "claims_reconciliation",
              "Apache-2.0 (synthetic data generated by this repository)",
              cases_sup[:42], cases_sup[42:63], cases_sup[63:], sup_card)

print("\nDone! Created 3 new datasets: legal_v1, insurance_v1, support_v1")
print("Run: forgebench validate-dataset legal_v1  (etc.) to confirm")
