.PHONY: install lint format typecheck test audit check

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

audit:
	uv run pip-audit

check: lint typecheck test
