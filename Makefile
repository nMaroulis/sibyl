.PHONY: setup api web docs check
setup:
	uv sync --group dev
	npm ci
api:
	uv run sibyl
web:
	npm run dev
docs:
	npm run docs:dev
check:
	uv run pytest
	uv run ruff check src tests
	npm run typecheck
	npm run build
	npm run docs:build
