DOCKER_IMAGE ?= aat-dev
DOCKER_AAT_HOME ?= $(HOME)/.aat
DOCKER_RUN = docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR)":/workspace -v "$(DOCKER_AAT_HOME)":/home/aat/.aat -w /workspace

test:
	pytest -q --disable-warnings --maxfail=1 --cov=aat --cov-report=term-missing

lint:
	ruff check aat tests

format:
	black aat tests

docker-build:
	mkdir -p "$(DOCKER_AAT_HOME)"
	docker build -t $(DOCKER_IMAGE) .

docker-test: docker-build
	mkdir -p "$(DOCKER_AAT_HOME)"
	$(DOCKER_RUN) --entrypoint make $(DOCKER_IMAGE) test

docker-lint: docker-build
	mkdir -p "$(DOCKER_AAT_HOME)"
	$(DOCKER_RUN) --entrypoint make $(DOCKER_IMAGE) lint

docker-review: docker-build
	@if [ -z "$(PROJECT_DIR)" ]; then echo "Usage: make docker-review PROJECT_DIR=<project_dir>"; exit 1; fi
	mkdir -p "$(DOCKER_AAT_HOME)"
	$(DOCKER_RUN) -p 8741:8741 $(DOCKER_IMAGE) review "$(PROJECT_DIR)" --host 0.0.0.0 --no-browser

.PHONY: test lint format docker-build docker-test docker-lint docker-review
