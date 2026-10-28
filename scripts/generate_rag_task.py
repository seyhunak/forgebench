#!/usr/bin/env python3
"""Generate the ``rag_knowledge`` custom task cases deterministically.

Each case gives the model a ``question`` plus ``retrieval_context`` chunks and
asks for an answer grounded only in that context. Ground truth (expected
answer, grounded flag, citations) is hand-authored and deterministic — never
produced by a model. The ``TaskCase.context`` field holds the ideal ground-truth
context (RAG goldens); ``TaskCase.retrieval_context`` holds what the RAG
pipeline actually retrieved and is used by the lexical faithfulness /
answer_relevancy / contextual_relevancy scoring rules.

Run with: python scripts/generate_rag_task.py
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "tasks" / "rag_knowledge"

# Knowledge base chunks. Index = chunk id used in citations.
CHUNKS = [
    "Refund policy: Customers may request a full refund within 30 days of purchase with original receipt.",
    "Shipping: Standard shipping takes 3-5 business days. Express shipping takes 1-2 business days. Overnight shipping available for urgent orders.",
    "PII: We do not store credit card numbers, social security numbers, or passwords in plain text. All sensitive data is encrypted.",
    "Support hours: Customer support is available Monday-Friday, 9am-6pm EST, excluding public holidays.",
    "Password reset: Use the 'Forgot Password' link on the login page to reset your password via email.",
    "Data retention: User account data is retained for 2 years after account closure, then anonymized.",
    "API rate limits: Free tier allows 1000 requests per hour. Paid tier allows 10000 requests per hour. Enterprise has custom limits.",
    "Account deletion: Accounts can be permanently deleted from Settings > Privacy > Delete Account. This action cannot be undone.",
    "Password requirements: Passwords must be at least 8 characters, include uppercase, lowercase, numbers, and symbols.",
    "International shipping: Available to 50+ countries. Customs duties and taxes are the recipient's responsibility.",
]

# (question, retrieval_context_indices, expected_answer, grounded, citation_indices, explanation)
CASES = [
    # ===== GROUNDED: answer supported by retrieved context =====
    ("How long do I have to request a refund?", [0],
     "You may request a full refund within 30 days of purchase with an original receipt.", True, [0],
     "Refund window is stated in the retrieved refund-policy chunk."),
    ("What are customer support hours?", [3],
     "Support is available Monday-Friday, 9am-6pm EST, excluding public holidays.", True, [3],
     "Support hours come straight from the retrieved support-hours chunk."),
    ("Do you store credit card numbers?", [2],
     "No. We do not store credit card numbers, social security numbers, or passwords in plain text.", True, [2],
     "PII chunk explicitly says sensitive data is not stored in plain text."),
    ("How do I reset my password?", [4],
     "Use the 'Forgot Password' link on the login page to reset your password via email.", True, [4],
     "Password-reset chunk gives the exact reset method."),
    ("Can I delete my account?", [7],
     "Yes. Accounts can be permanently deleted from Settings > Privacy > Delete Account, and this action cannot be undone.", True, [7],
     "Account-deletion chunk confirms deletion is possible and permanent."),
    ("What is the free-tier API rate limit?", [6],
     "The free tier allows 1000 requests per hour.", True, [6],
     "API rate-limits chunk states 1000 requests/hour for free tier."),
    ("Which countries can you ship to internationally?", [9],
     "International shipping is available to 50+ countries.", True, [9],
     "International-shipping chunk states 50+ countries."),
    ("How long does express shipping take?", [1],
     "Express shipping takes 1-2 business days.", True, [1],
     "Shipping chunk gives express as 1-2 business days."),
    ("How long is user data retained after closure?", [5],
     "User account data is retained for 2 years after account closure, then anonymized.", True, [5],
     "Data-retention chunk gives the 2-year retention period."),
    ("What are the password requirements?", [8],
     "Passwords must be at least 8 characters and include uppercase, lowercase, numbers, and symbols.", True, [8],
     "Password-requirements chunk lists all requirements."),
    ("Can I get a refund after 60 days?", [0],
     "No. Refunds are only available within 30 days of purchase with an original receipt.", True, [0],
     "The 30-day refund window means a 60-day request is out of policy."),
    ("Is overnight shipping available?", [1],
     "Yes. Overnight shipping is available for urgent orders.", True, [1],
     "Shipping chunk mentions overnight shipping for urgent orders."),
    ("Can support help on weekends?", [3],
     "No. Support is available Monday-Friday only, excluding public holidays.", True, [3],
     "Support-hours chunk is Monday-Friday only."),
    ("Is my social security number stored?", [2],
     "No. Social security numbers are not stored; all sensitive data is encrypted.", True, [2],
     "PII chunk says sensitive data is encrypted and not stored in plain text."),
    ("Can I undo an account deletion?", [7],
     "No. Account deletion cannot be undone.", True, [7],
     "Account-deletion chunk says the action cannot be undone."),
    ("Does the paid tier have a higher API limit?", [6],
     "Yes. The paid tier allows 10000 requests per hour versus 1000 for free.", True, [6],
     "API rate-limits chunk contrasts free (1000) and paid (10000) tiers."),
    ("Who pays customs duties on international orders?", [9],
     "The recipient is responsible for customs duties and taxes.", True, [9],
     "International-shipping chunk states the recipient pays customs."),
    ("Can I reset my password by phone?", [4],
     "No. Use the 'Forgot Password' link on the login page to reset via email.", True, [4],
     "Password-reset chunk specifies the email link method, not phone."),
    ("What happens to my data 2 years after I close my account?", [5],
     "It is anonymized after the 2-year retention period.", True, [5],
     "Data-retention chunk says data is anonymized after retention."),
    ("How long does standard shipping take?", [1],
     "Standard shipping takes 3-5 business days.", True, [1],
     "Shipping chunk gives standard as 3-5 business days."),
    ("Where can I delete my account?", [7],
     "From Settings > Privacy > Delete Account.", True, [7],
     "Account-deletion chunk gives the exact deletion path."),
    ("What is the minimum password length?", [8],
     "At least 8 characters.", True, [8],
     "Password-requirements chunk states the 8-character minimum."),
    ("Is enterprise API custom?", [6],
     "Yes. Enterprise has custom rate limits.", True, [6],
     "API rate-limits chunk mentions custom enterprise limits."),
    ("Are duties included in international shipping?", [9],
     "No. Customs duties and taxes are the recipient's responsibility.", True, [9],
     "International-shipping chunk says the recipient pays duties."),
    # ===== NOT GROUNDED: answer unsupported or contradicted by context =====
    ("What is the moon made of?", [0],
     "The moon is made of green cheese.", False, [],
     "The retrieved refund-policy chunk says nothing about the moon; the answer is unsupported."),
    ("What is the refund policy?", [],
     "You can get a full refund within 30 days.", False, [],
     "No context was retrieved, so the answer cannot be grounded (guardrail should flag)."),
    ("What are support hours?", [2],
     "Support is available Monday-Friday, 9am-6pm EST.", False, [],
     "The retrieved PII chunk says nothing about support hours; the answer is ungrounded."),
    ("How do I delete my account?", [7],
     "Accounts cannot be deleted under any circumstances.", False, [7],
     "The account-deletion chunk says deletion IS possible; the answer contradicts the context."),
    ("What is the shipping address?", [1],
     "Ship to 123 Main Street, Anytown.", False, [],
     "The shipping chunk contains no address; the answer invents one."),
    ("What is my account balance?", [6],
     "Your balance is $42.00.", False, [],
     "The API rate-limits chunk contains no account-balance information."),
    ("Can I get a refund?", [5],
     "Yes, refunds are always available.", False, [5],
     "The data-retention chunk says nothing about refunds; the claim is unsupported."),
    ("Is my password stored in plain text?", [3],
     "Yes, passwords are stored in plain text.", False, [2],
     "The PII chunk explicitly says passwords are NOT stored in plain text — direct contradiction."),
    ("How long is standard shipping?", [8],
     "Standard shipping takes 10 business days.", False, [1],
     "The shipping chunk says 3-5 days; the answer contradicts the retrieved context."),
    ("Do you offer international shipping?", [0],
     "Yes, to 50+ countries.", False, [],
     "The refund-policy chunk contains no international-shipping information."),
    ("Can I get cash back on returns?", [0],
     "Yes, cash back is available within 30 days.", False, [0],
     "The refund chunk mentions refunds, not cash back; the claim is unsupported."),
    ("What is the support email address?", [3],
     "Contact support@example.com.", False, [],
     "The support-hours chunk contains no email address."),
    ("Can I get a refund without a receipt?", [0],
     "Yes, a receipt is optional.", False, [0],
     "The refund chunk says an original receipt is required; the answer contradicts it."),
    ("Do you ship to Antarctica?", [9],
     "Yes, we ship to Antarctica.", False, [9],
     "The international-shipping chunk says 50+ countries but does not mention Antarctica."),
    # ===== REFUSAL: no context, model should decline =====
    ("What is the company CEO's name?", [],
     "I do not have enough information to answer that.", False, [],
     "No context retrieved; the model correctly refuses rather than guessing."),
    ("What is the refund deadline in days?", [0],
     "I do not have enough information to answer that.", False, [],
     "Refusal path to exercise the guardrail even when related context exists."),
    ("Who founded the company?", [],
     "I do not have that information.", False, [],
     "No context retrieved; the model correctly declines to answer."),
    ("Can I return an item?", [0],
     "Returns are handled as refunds within 30 days of purchase with an original receipt.", True, [0],
     "The refund-policy chunk covers returns as refunds within 30 days."),
    ("What is the return deadline in days?", [0],
     "Returns are accepted within 90 days.", False, [0],
     "The refund chunk says 30 days, not 90; the answer contradicts the context."),
    ("Can I contact support after hours?", [3],
     "No. Support is only available Monday-Friday, 9am-6pm EST.", True, [3],
     "The support-hours chunk limits support to weekdays 9am-6pm EST."),
    ("What is the product warranty period?", [5],
     "Products have a 1-year warranty.", False, [],
     "The data-retention chunk says nothing about warranties; the claim is unsupported."),
]

SPLIT_SIZES = {"train": 20, "dev": 10, "test": 15}


def write_jsonl(path: Path, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")


def main() -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    for idx, (question, rc_indices, answer, grounded, citations, explanation) in enumerate(CASES, start=1):
        retrieval_context = [CHUNKS[i] for i in rc_indices]
        context = retrieval_context
        record = {
            "id": f"RK-{idx:04d}",
            "input": {
                "question": question,
                "retrieval_context": retrieval_context,
            },
            "expected": {
                "answer": answer,
                "grounded": grounded,
                "citations": [str(c) for c in citations],
            },
            "context": context,
            "retrieval_context": retrieval_context,
            "notes": explanation,
        }
        all_records.append(record)

    assert len(all_records) == sum(SPLIT_SIZES.values()), (
        f"{len(all_records)} cases != {sum(SPLIT_SIZES.values())} split slots"
    )

    train = all_records[:SPLIT_SIZES["train"]]
    dev = all_records[SPLIT_SIZES["train"]:SPLIT_SIZES["train"] + SPLIT_SIZES["dev"]]
    test = all_records[SPLIT_SIZES["train"] + SPLIT_SIZES["dev"]:]

    for split_name, split_records in (("train", train), ("dev", dev), ("test", test)):
        write_jsonl(TASK_DIR / f"{split_name}.jsonl", split_records)
        print(f"wrote {TASK_DIR / f'{split_name}.jsonl'} ({len(split_records)} cases)")


if __name__ == "__main__":
    main()
