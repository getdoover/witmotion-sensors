FROM spaneng/doover_device_base AS base_image
LABEL com.doover.simulator="true"
LABEL com.doover.managed="true"

COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN uv venv --system-site-packages
COPY pyproject.toml /app/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r pyproject.toml

COPY . /app
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "main.py"]
