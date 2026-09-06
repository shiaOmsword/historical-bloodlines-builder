FROM python:3.13-slim-bookworm

ARG POETRY_VERSION=2.4.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    BLOODLINES_DATA_DIR=/data \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
        graphviz \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock README.md LICENSE ./
RUN poetry install --only main --no-root --no-ansi

COPY src ./src
COPY examples ./examples
RUN poetry install --only main --no-ansi

RUN mkdir -p /data/input /data/output \
    && fc-cache -f \
    && dot -V \
    && neato -V \
    && fc-match Sans \
    && python -c "import cairosvg; print('CairoSVG', cairosvg.__version__)"

ENTRYPOINT ["bloodlines"]
CMD ["--help"]
