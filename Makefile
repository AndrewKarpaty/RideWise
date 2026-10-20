.PHONY: install run test lint fmt typecheck seed clean

install:
	uv sync --extra dev

run:
	uv run streamlit run src/ridewise/ui/app.py

test:
	uv run pytest

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src/ridewise

seed:
	uv run python -m ridewise.seed

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache ridewise.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
