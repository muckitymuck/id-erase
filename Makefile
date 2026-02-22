.PHONY: build up down migrate test logs clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

migrate:
	docker compose exec erasure-executor alembic -c /app/alembic.ini upgrade head

test:
	cd packages/erasure-executor && python -m pytest tests/ -v

logs:
	docker compose logs -f erasure-executor

clean:
	docker compose down -v

healthz:
	curl -s http://localhost:8080/healthz | python -m json.tool
