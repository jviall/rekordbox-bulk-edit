.PHONY: test coverage lint format install-hooks run-hooks

test:
	uv run pytest tests

coverage:
	uv run pytest tests --cov=rekordbox_bulk_edit --junitxml=.coverage/junit.xml --cov-report=term-missing --cov-report=html --cov-report=xml

lint:
	uv run ruff check --fix

format:
	uv run ruff format

install-hooks:
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

run-hooks:
	uv run pre-commit run --all-files
