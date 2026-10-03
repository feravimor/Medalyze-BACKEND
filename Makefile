.PHONY: up down migrate test lint typecheck contract check db-reset

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy app scripts

contract:
	python scripts/verificar_openapi.py

check: lint typecheck contract test

db-reset:
	docker compose down -v
	docker compose up --build
