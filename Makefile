.PHONY: install test typecheck lint

install:
	pip install -e ".[dev]"

test:
	pytest -q

typecheck:
	mypy --strict src/aibi_dax/

lint:
	ruff check src/ tests/
