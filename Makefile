.PHONY: sync test bench lint

sync:
	uv sync

test:
	uv run pytest

bench:
	uv run pytest benchmarks -o addopts= --benchmark-only --benchmark-group-by=func --benchmark-columns=mean,stddev,rounds

lint:
	uv run ruff check src tests benchmarks
	uv run ruff format --check src tests benchmarks
