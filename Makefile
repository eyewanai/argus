run:
	uv run argus

fmt:
	uv run ruff format .

lint:
	uv run ruff check .

fix:
	uv run ruff check --fix .

pre-commit:
	uv run pre-commit run --all-files

graph:
	uv run python scripts/draw_graph.py
