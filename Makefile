.PHONY: install test lint format data check-data demo dashboard clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests scripts examples

format:
	ruff format src tests scripts examples

# Regenerate the synthetic dataset deterministically (same seed, same data).
data:
	python scripts/generate_dataset.py --seed 42 --train 100 --dev 40 --test 60

# Regenerate everything that has a generator and fail if committed data differs.
# healthcare_v1 and ecommerce_v1 have no generator; tests/test_run_integrity.py pins them.
check-data:
	python scripts/generate_dataset.py --seed 42 --train 100 --dev 40 --test 60
	python scripts/generate_multi_dataset.py
	python scripts/generate_more_datasets.py
	python scripts/generate_rag_task.py
	python scripts/generate_guardrails_task.py
	@test -z "$$(git status --porcelain -- datasets tasks)" || { git status --short -- datasets tasks; echo "regenerated data differs from the committed data"; exit 1; }

# End-to-end pipeline using the deterministic mock provider. No API key needed.
demo:
	forgebench validate-dataset finance_v1
	forgebench run --config configs/baseline.yaml --run-id baseline-v1-mock
	forgebench run --config configs/experiments/prompt_v1.yaml --run-id prompt-v1-mock
	forgebench compare runs/baseline-v1-mock runs/prompt-v1-mock

# Local web UI (BYOK key field, run launcher, results viewer).
dashboard:
	forgebench dashboard

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache

# Stripe credit service (same process devctl manages on :8583)
stripe:
	.venv/bin/python -m services.stripe_webhook
