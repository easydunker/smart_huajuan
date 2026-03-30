test:
	pytest -q --disable-warnings --maxfail=1 --cov=aat --cov-report=term-missing

lint:
	ruff check aat tests

format:
	black aat tests

.PHONY: test lint format
