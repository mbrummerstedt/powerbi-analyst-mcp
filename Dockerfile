FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY powerbi_mcp/*.py powerbi_mcp/
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --no-editable --no-cache

ENV PATH="/app/.venv/bin:${PATH}"
ENTRYPOINT ["powerbi-analyst-mcp"]
