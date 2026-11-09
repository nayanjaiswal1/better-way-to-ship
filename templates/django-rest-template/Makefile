.DEFAULT_GOAL := help

.PHONY: help install-dev dev migrate makemigrations test test-cov lint format typecheck security audit clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install-dev: ## Install all dependencies including dev
	uv sync --all-extras

dev: ## Run development server
	uv run python src/manage.py runserver 0.0.0.0:8000

migrate: ## Apply all migrations
	uv run python src/manage.py migrate

makemigrations: ## Generate new migrations
	uv run python src/manage.py makemigrations

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing --cov-report=xml --junit-xml=report.xml -n auto

lint: ## Lint and format check
	uv run ruff check src tests
	uv run ruff format --check src tests

format: ## Auto-fix lint and format
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck: ## Run mypy type checking
	uv run mypy src

security: ## Run security checks (via ruff S rules)
	uv run ruff check --select S src

audit: ## Audit dependencies for vulnerabilities
	uv run pip-audit

clean: ## Remove cache and build artifacts
	rm -rf .uv-cache .ruff_cache .mypy_cache .pytest_cache __pycache__ coverage.xml report.xml
