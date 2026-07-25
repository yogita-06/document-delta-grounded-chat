.PHONY: install samples run test eval demo
install:
	python -m pip install -e ".[dev]"
samples:
	python scripts/generate_samples.py
run:
	uvicorn apps.api.main:app --reload
test:
	python -m pytest
eval: samples
	python -m eval.run_eval
demo: samples
	uvicorn apps.api.main:app --reload
