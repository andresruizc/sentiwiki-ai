SHELL := /bin/bash

ifeq (,$(wildcard .env))
$(error .env file is missing. Please create one based on .env.example)
endif

include .env

CHECK_DIRS := .

.PHONY: \
	help init test \
	dev-api dev-frontend \
	format-fix lint-fix format-check lint-check \
	scrape-dataspace enhance-sentiwiki enhance-dataspace \
	test-retriever test-rag test-metadata-filtering \
	eval-ragas eval-ragas-latency compare-filtering \
	preload-models \
	docker-build docker-up docker-stop docker-down

help:
	@echo "SentiWiki AI – main commands"
	@echo "  make init                    # uv venv + install .[dev]"
	@echo "  make test                    # pytest"
	@echo "  make dev-api                 # uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload"
	@echo "  make dev-frontend            # npm run dev (in frontend/)"
	@echo "  make format-fix              # ruff format + import sort + fix"
	@echo "  make lint-fix                # ruff check --fix"
	@echo "  make format-check            # ruff format/check + lint (no changes)"
	@echo "  make lint-check              # ruff lint only"
	@echo "  make scrape-dataspace        # uv run scripts/data/scrape_dataspace.py"
	@echo "  make enhance-sentiwiki       # uv run scripts/data/enhance_sentiwiki.py"
	@echo "  make enhance-dataspace       # uv run scripts/data/enhance_dataspace.py"
	@echo "  make test-retriever          # uv run scripts/experiments/test_retriever.py"
	@echo "  make test-rag                # uv run scripts/experiments/test_rag_litellm.py"
	@echo "  make test-metadata-filtering # uv run scripts/experiments/test_metadata_filtering.py"
	@echo "  make eval-ragas              # uv run scripts/evaluation/eval_ragas.py (small run)"
	@echo "  make eval-ragas-latency      # uv run scripts/evaluation/eval_ragas_with_latency.py"
	@echo "  make compare-filtering       # uv run scripts/experiments/compare_filtering.py"
	@echo "  make preload-models          # uv run scripts/setup/preload_models.py"
	@echo "  make docker-build            # docker compose build (in docker/)"
	@echo "  make docker-up               # docker compose up --build -d (in docker/)"
	@echo "  make docker-stop             # docker compose stop (in docker/)"
	@echo "  make docker-down             # docker compose down (in docker/)"

init:
	uv venv || true
	uv pip install -e ".[dev]"

test:
	uv run pytest

dev-api:
	uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload

dev-frontend:
	cd frontend && npm run dev

format-fix:
	uv run ruff format $(CHECK_DIRS)
	uv run ruff check --select I --fix $(CHECK_DIRS)

lint-fix:
	uv run ruff check --fix $(CHECK_DIRS)

format-check:
	uv run ruff format --check $(CHECK_DIRS)
	uv run ruff check -e $(CHECK_DIRS)
	uv run ruff check --select I -e $(CHECK_DIRS)

lint-check:
	uv run ruff check $(CHECK_DIRS)

scrape-dataspace:
	uv run python scripts/data/scrape_dataspace.py

enhance-sentiwiki:
	uv run python scripts/data/enhance_sentiwiki.py

enhance-dataspace:
	uv run python scripts/data/enhance_dataspace.py

test-retriever:
	uv run python scripts/experiments/test_retriever.py -i

test-rag:
	uv run python scripts/experiments/test_rag_litellm.py -i

eval-ragas:
	uv run python scripts/evaluation/eval_ragas.py --collection sentiwiki_index --limit 10 --delay 10.0

docker-build:
	cd deployment/docker && docker compose build

docker-up:
	cd deployment/docker && docker compose up --build -d

docker-stop:
	cd deployment/docker && docker compose stop

docker-down:
	cd deployment/docker && docker compose down


