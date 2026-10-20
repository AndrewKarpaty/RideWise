.PHONY: install run api web dev build test lint fmt typecheck seed clean

install:
	uv sync --extra dev
	cd web && npm install

# --- running ---------------------------------------------------------------

# The React app. Needs `make api` in another terminal.
web:
	cd web && npm run dev

# The HTTP API on :8000. Serves web/dist too, once it is built.
api:
	uv run uvicorn ridewise.api:app --reload --port 8000

# Both at once, API in the background.
dev:
	uv run uvicorn ridewise.api:app --reload --port 8000 & \
	cd web && npm run dev

# The original Streamlit UI, still here and still works.
run:
	uv run streamlit run src/ridewise/ui/app.py

build:
	cd web && npm run build

# --- checks ----------------------------------------------------------------

test:
	uv run pytest

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src/ridewise
	cd web && npm run typecheck

seed:
	uv run python -m ridewise.seed

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache web/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
