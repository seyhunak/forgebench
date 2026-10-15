.PHONY: install test lint format data demo clean

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

# End-to-end pipeline using the deterministic mock provider. No API key needed.
demo:
	forgebench validate-dataset finance_v1
	forgebench run --config configs/baseline.yaml --run-id baseline-v1-mock
	forgebench run --config configs/experiments/prompt_v1.yaml --run-id prompt-v1-mock
	forgebench compare runs/baseline-v1-mock runs/prompt-v1-mock

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
