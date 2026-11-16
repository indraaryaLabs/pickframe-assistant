.PHONY: setup lint test eval report check

setup:
	python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'

lint:
	ruff check . && ruff format --check . && mypy

test:
	pytest --cov --cov-fail-under=95

# Scores the assistant on every labelled case and fails when a gated metric regresses.
eval:
	pickframe-assistant eval --check

# Regenerates the static evaluation report in site/.
report:
	pickframe-assistant eval --report site

check: lint test eval
