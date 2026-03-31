# AAT - Academic AI Translator

Local-first CLI tool for translating academic documents from English to Chinese.

## Features

- Local PDF/DOCX library ingestion for reference-aware workflows
- Translation checkpoints plus a browser review UI
- Docker workflow for CLI commands, tests, lint, and review
- Current end-to-end `aat translate` CLI path is Anthropic-oriented

## Installation

### Local

```bash
pip install -e ".[dev]"
```

### Docker

```bash
make docker-build
```

## Local Usage

```bash
aat init
aat add-library paper.pdf
aat review project-folder
```

## Development

```bash
make test
make lint
make format
```

## Docker Workflow

The standard container contract is:

- Repo mount: `/workspace`
- Persistent AAT data mount: `/home/aat/.aat`
- Review UI port: `8741`
- Project checkpoints stay under the mounted repo unless you add a separate override later

The image defaults to a non-root `aat` user, and the provided Make targets still pass `--user "$(id -u):$(id -g)"` so bind-mounted repo writes stay owned by the host user on Linux.

### Core Commands

```bash
# Build the image
make docker-build

# Run CLI help from the container
mkdir -p "$HOME/.aat"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD":/workspace \
  -v "$HOME/.aat":/home/aat/.aat \
  -w /workspace \
  aat-dev --help

# Run the test suite in the container
make docker-test

# Run lint in the container
make docker-lint

# Launch the review UI from the container
make docker-review PROJECT_DIR=path/to/project
```

Then open `http://127.0.0.1:8741` in the host browser.

### Runtime Environment Variables

- Pass secrets at runtime with exported environment variables or `docker run --env-file ...`; the image does not bake credentials.
- `ANTHROPIC_API_KEY`: primary auth path for the current `aat translate` CLI flow
- `ANTHROPIC_AUTH_TOKEN`: alternative auth token for Anthropic-compatible endpoints
- `ANTHROPIC_BASE_URL`: custom Anthropic-compatible base URL
- `OPENAI_API_KEY`: not part of the current Docker happy path; only relevant if broader OpenAI CLI wiring is added later

### State and Provider Caveats

- The persisted library under `~/.aat/library` affects later runs. If you want isolated demos, point `DOCKER_AAT_HOME` at a separate directory, for example `DOCKER_AAT_HOME=$PWD/.aat-demo make docker-test`.
- The current `aat translate` CLI path still hard-codes the Anthropic provider. Docker support does not change that provider behavior.
- Ollama is not bundled into this image. If you test local-only services from inside Docker, use an explicit host address such as `host.docker.internal` or your host machine's reachable IP.

## Project Status

- Core CLI, review UI, and export flows exist in the repo today.
- Some roadmap items and provider paths are still partial; the Docker workflow above documents only the supported happy path.
