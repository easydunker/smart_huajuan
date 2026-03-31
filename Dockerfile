FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/aat

WORKDIR /workspace

RUN . /etc/os-release \
    && printf 'deb http://deb.debian.org/debian %s main\n' "$VERSION_CODENAME" > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y -o Acquire::Retries=5 --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /home/aat --shell /bin/bash aat \
    && chmod 755 /home/aat

COPY . /workspace

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -e ".[dev]" \
    && mkdir -p /home/aat/.aat \
    && chown -R aat:aat /workspace /home/aat

USER aat

EXPOSE 8741

ENTRYPOINT ["aat"]
