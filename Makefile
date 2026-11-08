.PHONY: install test coverage typecheck lint

install:
	pip install -e ".[dev]"

test:
	pytest -q

coverage:
	pytest --cov=src/aibi_dax --cov-report=term-missing -q

typecheck:
	mypy --strict src/aibi_dax/

lint:
	ruff check src/ tests/
