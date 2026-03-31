# Docker Container Image Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reproducible Docker-based runtime for AAT so developers can run CLI commands, tests, and the review UI without installing project dependencies on the host.

**Architecture:** Build one Python 3.11 image from repo sources using `pip install -e ".[dev]"`. Keep the image focused on developer/runtime parity, not production hardening. Make a small set of container-aware application changes so writable data paths, browser launch behavior, and review UI binding work cleanly inside Docker.

**Tech Stack:** Docker, `python:3.11-slim`, Hatchling editable install, Click CLI, FastAPI/Uvicorn, GitHub Actions

---

## Chunk 1: Scope and Runtime Contract

### Planned File Changes

- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `aat/runtime_paths.py`
- Create: `tests/test_runtime_paths.py`
- Modify: `aat/cli.py`
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_cli.py`

### Repo Facts This Plan Must Respect

- Python baseline is `3.11` in [`pyproject.toml`](../pyproject.toml) and `.github/workflows/ci.yml`; the image should match that version.
- The app currently writes persistent user data under `Path.home() / ".aat"` in [`aat/cli.py`](../aat/cli.py).
- Project checkpoint state is created relative to `Path.cwd() / "projects"` in [`aat/storage/checkpoints.py`](../aat/storage/checkpoints.py).
- The review UI currently binds to `127.0.0.1` and calls `webbrowser.open()` in [`aat/cli.py`](../aat/cli.py), which is not container-friendly.
- `add-library` depends on `PyPDF2` at runtime and `review` depends on `uvicorn`, but those imports are not declared in [`pyproject.toml`](../pyproject.toml).
- The repo contains a checked-in `venv/`, local artifacts, checkpoints, outputs, and generated `.docx` files, so `.dockerignore` is mandatory to keep build context sane.

### Functional Contract

- The image must support these commands without extra host Python setup:
  - `aat --help`
  - `aat init`
  - `aat add-library <file-or-dir>`
  - `aat review <project_dir> --host 0.0.0.0 --no-browser`
  - `make test`
  - `make lint`
- The image must not bake secrets. API keys stay runtime-only via environment variables or `--env-file`.
- Persistent user data must survive container recreation.
- Bind-mounted repo commands must not leave root-owned files behind on Linux hosts.
- The documented workflow must either run as a non-root user by default or use a documented `--user` strategy in wrapper commands.
- The plan should document one standard runtime contract:
  - Repo mounted at `/workspace`
  - User data mounted at `/home/aat/.aat`
  - Review UI exposed with `-p 8741:8741`
  - Project checkpoints stored under the mounted repo unless an override is configured

### Out of Scope

- Publishing images to a registry
- Docker Compose, Kubernetes, or deployment orchestration
- GPU support or running Ollama inside the same container
- Production image minimization or hardening beyond normal developer safety

---

## Chunk 2: Implementation Tasks

### Task 1: Centralize Runtime Paths and Container-Safe CLI Behavior

**Files:**
- Create: `aat/runtime_paths.py`
- Modify: `aat/cli.py`
- Test: `tests/test_runtime_paths.py`
- Test: `tests/test_cli.py`

- [x] Add a small path helper module that owns all runtime directory decisions.
- [x] Define helpers for:
  - `AAT_HOME` defaulting to `Path.home() / ".aat"`
  - `AAT_LIBRARY_DIR`
  - `AAT_OUTPUT_DIR`
  - `AAT_PROJECTS_DIR` defaulting to `Path.cwd() / "projects"`
- [x] Update CLI commands in `aat/cli.py` to use the helper instead of hard-coded `Path.home()` and `Path.cwd()` logic.
- [x] Extend `aat review` with `--host` and `--no-browser` flags.
- [x] Keep host defaults friendly for local non-Docker use, but allow container docs to run `--host 0.0.0.0 --no-browser`.
- [x] Add tests that prove env overrides work and that review mode can skip `webbrowser.open()`.

**Acceptance criteria:**
- `tests/test_runtime_paths.py -q` passes.
- `tests/test_cli.py -q` passes with new coverage for path overrides and browser suppression.
- No CLI path still reaches directly for `Path.home() / ".aat"` or `Path.cwd() / "projects"` outside the helper module.

**Task 1 verification note (2026-03-31):**
- `./venv/bin/pytest -q tests/test_runtime_paths.py tests/test_cli.py` passed (`46 passed`)
- `./venv/bin/python -m aat --help` passed

### Task 2: Fix Packaging Gaps for Containerized CLI Paths

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`
- Test: `tests/test_milestone5/test_ingestion.py`
- Test: `tests/test_ui/test_server.py`

- [x] Audit runtime imports used by documented CLI commands against declared dependencies.
- [x] Add missing runtime dependencies required by the advertised CLI surface:
  - `PyPDF2` for `aat add-library`
  - `uvicorn` for `aat review`
- [x] Do not move test-only tools out of the `dev` extra.
- [x] Verify `pip install -e ".[dev]"` produces a working image for both CLI use and test execution.
- [x] Document any provider-related gaps discovered during the audit.

**Acceptance criteria:**
- A fresh install inside the image can execute `aat add-library` and `aat review` without `ImportError`.
- The README and spec do not claim broader provider behavior than the code actually supports.

**Task 2 verification note (2026-03-31):**
- `./venv/bin/python -m pip install -e ".[dev]"` passed in the repo virtualenv
- `./venv/bin/pytest -q tests/test_milestone5/test_ingestion.py tests/test_ui/test_server.py` passed (`42 passed`)
- `PyPDF2` and `uvicorn` are declared in [`pyproject.toml`](../pyproject.toml)
- `aat/ui/server.py` now passes `request=...` explicitly to `TemplateResponse`, which keeps the review UI compatible with the freshly resolved `fastapi`/`starlette` stack in the image
- `docker run --rm --entrypoint pytest aat-dev tests/test_ui/test_server.py -q` passed (`16 passed`)

### Task 3: Add Docker Build Assets

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [x] Create a single developer/runtime Docker image based on `python:3.11-slim`.
- [x] Set `WORKDIR /workspace`.
- [x] Install the project with `pip install -e ".[dev]"`.
- [x] Keep the runtime simple:
  - `PYTHONDONTWRITEBYTECODE=1`
  - `PYTHONUNBUFFERED=1`
  - `PIP_DISABLE_PIP_VERSION_CHECK=1`
- [x] Prefer a non-root default user if write access to the mounted workspace and home directory remains predictable; otherwise document the required `docker run --user ...` contract in `Makefile` and `README.md`.
- [x] Use `ENTRYPOINT ["aat"]` so `docker run <image> ...` maps directly to CLI subcommands.
- [x] Add a `.dockerignore` that excludes at minimum:
  - `.git/`
  - `venv/`
  - `.pytest_cache/`
  - `.hypothesis/`
  - `__pycache__/`
  - `checkpoints/`
  - `projects/`
  - `outputs/`
  - `*.docx`
  - `.coverage`
- [x] Keep system package installation minimal. Only add `apt` packages if the image build or runtime proves they are required.

**Acceptance criteria:**
- `docker build -t aat-dev .` succeeds from a clean checkout.
- `docker run --rm aat-dev --help` succeeds.
- `docker run --rm aat-dev init` succeeds.

**Task 3 verification note (2026-03-31):**
- `docker build -t aat-dev .` passed
- Docker build context transfer was `5.58MB`, which indicates [`.dockerignore`](../.dockerignore) is filtering local artifacts materially
- `docker run --rm aat-dev --help` passed
- `docker run --rm aat-dev init` passed
- `docker run --rm --entrypoint id aat-dev` reported `uid=1000(aat) gid=1000(aat)`
- `docker run --rm --user "$(id -u):$(id -g)" ... touch /workspace/.docker-own-test` preserved host ownership (`501:20` in this environment)
- [`Dockerfile`](../Dockerfile) now rewrites apt sources to the distro's main Debian repo and enables retry logic so transient `trixie-updates`/security mirror failures do not block developer builds
- [`Dockerfile`](../Dockerfile) now keeps `/home/aat` at mode `755`, which allows the documented `--user "$(id -u):$(id -g)"` workflow to traverse into the mounted `/home/aat/.aat`

### Task 4: Add Documented Container Workflows

**Files:**
- Modify: `Makefile`
- Modify: `README.md`

- [x] Add Docker helper targets to `Makefile` for the standard workflows:
  - `docker-build`
  - `docker-test`
  - `docker-lint`
  - `docker-review`
- [x] In Make targets that write to the bind-mounted repo, avoid creating root-owned files.
- [x] Document the standard mounts in `README.md`:
  - repo -> `/workspace`
  - host `~/.aat` -> `/home/aat/.aat`
  - optional port mapping for review UI
- [x] Call out that the persisted library volume influences future `translate` runs, so examples should either use an isolated AAT data directory for demos or explain the shared-state behavior plainly.
- [x] Document runtime env vars:
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_AUTH_TOKEN`
  - `ANTHROPIC_BASE_URL`
  - `OPENAI_API_KEY` if still relevant after the packaging audit
- [x] Add examples for:
  - build
  - run CLI help
  - run tests in container
  - launch review UI from container
- [x] Call out that local-only services such as host Ollama require an explicit host address such as `host.docker.internal` and are not bundled into this image.
- [x] Do not document placeholder behavior as if it is production-ready; keep examples aligned with what `aat translate` and related commands actually do today.

**Acceptance criteria:**
- A developer can follow the README and run the core workflows without guessing mount points or flags.
- The `Makefile` commands are copy-paste-safe for the standard happy path.

**Task 4 verification note (2026-03-31):**
- `PATH="/Users/yingyi/personal/smart_huajuan/venv/bin:$PATH" make test` passed locally (`577 passed, 1 skipped`)
- `make docker-test` passed (`577 passed, 1 skipped`)
- `make docker-lint` runs correctly inside Docker but still fails on the repo's pre-existing Ruff baseline (`262` violations), matching the known host lint state rather than a Docker wiring issue
- `make -n docker-review PROJECT_DIR="/tmp/example project"` preserved quoting for project paths with spaces
- `docker run -d ... aat-dev review /tmp/project --host 0.0.0.0 --no-browser` served `/api/status`; the host probe required `curl --noproxy '*'` in this environment because a local proxy otherwise returned `502`
- [`README.md`](../README.md) now states that secrets must be provided at runtime via environment variables or `--env-file`

### Task 5: Keep Docker Support Healthy in CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [x] Add a Docker smoke job or post-test step in CI.
- [x] Build the image in CI.
- [x] Run a minimal smoke check with the built image:
  - `aat --help`
  - `aat init`
- [x] Run at least one targeted in-container verification command using the installed dev dependencies, for example:
  - `pytest tests/test_cli.py -q`
  - or a smaller container-focused subset if startup time becomes an issue
- [x] Keep the existing host-based test/lint checks intact.

**Acceptance criteria:**
- CI fails if the Docker image stops building or the containerized CLI becomes unusable.
- CI duration stays reasonable; do not duplicate the full host test suite inside Docker unless it is justified by a concrete gap.

**Task 5 verification note (2026-03-31):**
- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) now runs the containerized slice `tests/test_runtime_paths.py tests/test_cli.py tests/test_ui/test_server.py -q`
- The equivalent local command passed: `docker run --rm --entrypoint pytest aat-dev tests/test_runtime_paths.py tests/test_cli.py tests/test_ui/test_server.py -q` (`62 passed`)

---

## Chunk 3: Verification, Risks, and Delivery Checklist

### Verification Commands

- [ ] Host verification:
  - `pytest -q tests/test_runtime_paths.py tests/test_cli.py`
  - `pytest -q tests/test_milestone5/test_ingestion.py tests/test_ui/test_server.py`
  - `make test`
  - `make lint`
  - Note: targeted pytest slices and `PATH="/Users/yingyi/personal/smart_huajuan/venv/bin:$PATH" make test` now pass locally; `make lint` still fails on the repo's pre-existing Ruff baseline outside this Docker-focused change set.
- [x] Docker verification:
  - `docker build -t aat-dev .`
  - `docker run --rm aat-dev --help`
  - `docker run --rm aat-dev init`
  - `docker run --rm --entrypoint pytest aat-dev tests/test_cli.py -q`
  - `docker run --rm --entrypoint pytest aat-dev tests/test_runtime_paths.py tests/test_cli.py tests/test_ui/test_server.py -q`
  - Note: Dockerfile build reliability was improved by pinning apt to the distro's main Debian repo and enabling retries for the remaining network fetches.
- [x] Manual review UI smoke:
  - `docker run --rm -it -p 8741:8741 -v "$PWD":/workspace -v "$HOME/.aat":/home/aat/.aat aat-dev review <project_dir> --host 0.0.0.0 --no-browser`
  - Verified with a real checkpointed project using `curl --noproxy '*' http://127.0.0.1:8741/api/status` because the default host proxy in this environment returned `502`

### Risks to Call Out During Implementation

- [x] The current `translate` command is still tightly coupled to Anthropic in `aat/cli.py`; Docker support should not be documented as solving provider configurability.
- [x] The persisted library under `~/.aat/library` affects later translations, so shared demo data can make container examples look nondeterministic.
- [x] File ownership on bind mounts can become messy; verify the chosen `docker run` strategy does not create permission problems.
- [x] Review UI browser auto-open must remain friendly on host installs while being suppressible in containers.
- [x] The repo has a large local footprint; verify `.dockerignore` materially reduces build context.

### Final Delivery Checklist

- [x] `Dockerfile` exists and builds
- [x] `.dockerignore` excludes local artifacts and virtualenv content
- [x] container-aware path helpers exist and are tested
- [x] `aat review` works with `--host` and `--no-browser`
- [x] missing runtime dependencies are declared
- [x] `Makefile` has Docker helper targets
- [x] `README.md` documents the standard container workflows
- [x] CI builds and smoke-tests the image
- [x] no secrets are baked into the image or docs
