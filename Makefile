.PHONY: test test-e2e test-e2e-docker test-e2e-snapshot-update coverage lint format typecheck install-hooks run-hooks

test:
	uv run pytest tests

test-e2e:
	uv run pytest tests/e2e

test-e2e-docker:
	docker compose run --rm e2e

test-e2e-snapshot-update:
	docker compose run --rm e2e uv run pytest tests/e2e --snapshot-update

watch:
	uv run ptw .

coverage:
	uv run pytest tests --cov=rekordbox_edit --junitxml=.coverage/junit.xml --cov-report=term-missing --cov-report=html --cov-report=xml

lint:
	uv run ruff check --fix

format:
	uv run ruff format

typecheck:
	uv run ty check

install-hooks:
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

run-hooks:
	uv run pre-commit run --all-files
