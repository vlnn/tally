.PHONY: test lint build check clean

SMOKE_PYTHON ?= /usr/bin/env python3

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

build:
	uv run --python 3.13 python -m hoard.build

check: build
	uv run --python 3.13 python -m hoard.build --check
	$(SMOKE_PYTHON) scripts/smoke.py dist/tally.alfredworkflow

clean:
	rm -rf dist .pytest_cache .ruff_cache .mypy_cache
